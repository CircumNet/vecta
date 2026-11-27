"""
Business rules for leave. Every state change goes through this module so the
rules are enforced in one place (not in views, not in the frontend).
"""
import datetime as dt
import os
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import Roles, User

from .models import BlackoutPeriod, Delegation, Holiday, LeaveAction, LeaveBalance, LeaveRequest, LeaveType, Notification

Status = LeaveRequest.Status
Action = LeaveAction.Action
FULL = LeaveRequest.DayPart.FULL

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
APPROVER_ROLES = {Roles.DEPARTMENT_HEAD, Roles.HR_MANAGER, Roles.ADMIN}
HR_THRESHOLD_DAYS = 14

# ---------------------------------------------------------------- helpers
def count_working_days(start, end, day_part=FULL):
    """Mon-Fri days between start and end inclusive, minus public holidays. A half day counts 0.5."""
    holidays = set(Holiday.objects.filter(date__range=(start, end)).values_list("date", flat=True))
    days, day = Decimal(0), start
    while day <= end:
        if day.weekday() < 5 and day not in holidays:
            days += 1
        day += dt.timedelta(days=1)
    if day_part != FULL and start == end:
        days *= Decimal("0.5")
    return days


def notify(user, kind, message, leave_request=None):
    Notification.objects.create(user=user, kind=kind, message=message[:300], leave_request=leave_request)
    if user.email and user.email_notifications:
        transaction.on_commit(
            lambda: send_mail(
                f"[Vecta] {message[:70]}", message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True
            )
        )


def _log(req, actor, action, comment=""):
    LeaveAction.objects.create(leave_request=req, actor=actor, action=action, comment=comment or "")


def _get_balance(user, leave_type, year):
    balance, _ = LeaveBalance.objects.get_or_create(
        user=user, leave_type=leave_type, year=year, defaults={"entitled": leave_type.default_days}
    )
    return balance


def _locked_balance(user, leave_type, year):
    balance, _ = LeaveBalance.objects.select_for_update().get_or_create(
        user=user, leave_type=leave_type, year=year, defaults={"entitled": leave_type.default_days}
    )
    return balance


def ensure_balances(user, year=None):
    """Create any missing balance rows for the year, then return them."""
    year = year or timezone.localdate().year
    for lt in LeaveType.objects.filter(is_active=True):
        _get_balance(user, lt, year)
    return LeaveBalance.objects.filter(user=user, year=year, leave_type__is_active=True).select_related("leave_type")


def _lock(req):
    return LeaveRequest.objects.select_for_update().select_related("user", "leave_type").get(pk=req.pk)


def resolve_approver(user):
    """Department head approves leave. Nobody approves their own request."""
    dept_head = user.department.head if user.department_id else None
    if dept_head and dept_head.pk != user.pk and dept_head.is_active:
        return dept_head
    raise ValidationError({
        "detail": "No department head is configured for your account. Please contact HR."
    })

def active_delegators(user, on=None):
    """Ids of approvers who have handed their queue to `user` today."""
    on = on or timezone.localdate()
    return list(
        Delegation.objects.filter(delegate=user, is_active=True, start_date__lte=on, end_date__gte=on)
        .values_list("delegator_id", flat=True)
    )


# Update can_decide
def can_decide(req, actor):
    if req.user_id == actor.pk:
        return False
    if req.status == Status.AWAITING_HR:
        return actor.is_hr
    return req.current_approver_id == actor.pk or req.current_approver_id in active_delegators(actor)

def can_view(req, user):
    if req.user_id == user.pk or req.current_approver_id == user.pk or user.is_hr:
        return True
    owner = req.user
    if owner.department_id and owner.department.head_id == user.pk:
        return True
    if req.current_approver_id in active_delegators(user):
        return True
    return req.actions.filter(actor=user).exists()


def on_leave_today(user):
    """Approved leave covering today. HR sees everyone; department heads see their own people."""
    today = timezone.localdate()
    qs = LeaveRequest.objects.filter(
        status=Status.APPROVED,
        start_date__lte=today,
        end_date__gte=today,
    )
    if not user.is_hr:
        qs = qs.filter(user__department__head=user)
    return qs.select_related("user", "user__department", "leave_type")

def _validate_attachment(f):
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError({"attachment": f"Allowed file types: {', '.join(sorted(ALLOWED_EXTENSIONS))}."})
    if f.size > MAX_UPLOAD_BYTES:
        raise ValidationError({"attachment": "File is larger than 5 MB."})
    signatures = {
        ".pdf": (b"%PDF-",),
        ".jpg": (b"\xff\xd8\xff",),
        ".jpeg": (b"\xff\xd8\xff",),
        ".png": (b"\x89PNG\r\n\x1a\n",),
    }
    try:
        header = f.read(8)
        f.seek(0)
    except (AttributeError, OSError):
        raise ValidationError({"attachment": "The uploaded file could not be read."})
    if not any(header.startswith(signature) for signature in signatures[ext]):
        raise ValidationError({"attachment": "The file contents do not match the selected file type."})


def _flatten(detail):
    if isinstance(detail, dict):
        return [m for v in detail.values() for m in _flatten(v)]
    if isinstance(detail, (list, tuple)):
        return [m for v in detail for m in _flatten(v)]
    return [str(detail)]


def _require_pending_approver(req, actor):
    if req.status != Status.PENDING:
        raise ValidationError({"detail": f"This request is already {req.status}."})
    if not can_decide(req, actor):
        raise PermissionDenied("You are not the approver for this request.")


def _on_behalf(req, actor, comment):
    if req.current_approver_id != actor.pk and req.current_approver:
        return f"[on behalf of {req.current_approver.display_name}] {comment or ''}".strip()
    return comment


def _check(*, user, leave_type, start_date, end_date, day_part=FULL, attachment=None, relief_officer=None,
           check_document=True, lock=False, create_balance=True):
    """All submission rules. Raises ValidationError; returns (days, approver, balance)."""
    today = timezone.localdate()
    if end_date < start_date:
        raise ValidationError({"end_date": "End date cannot be before start date."})
    if start_date < today:
        raise ValidationError({"start_date": "Start date cannot be in the past."})
    if start_date.year != end_date.year:
        raise ValidationError({"detail": "Leave across two calendar years must be submitted as two requests."})
    if day_part != FULL and start_date != end_date:
        raise ValidationError({"day_part": "Half-day leave is only available for a single day."})
    days = count_working_days(start_date, end_date, day_part)
    if days == 0:
        raise ValidationError({"detail": "The selected dates contain no working days."})

    if leave_type.min_notice_days and (start_date - today).days < leave_type.min_notice_days:
        raise ValidationError({"start_date": f"{leave_type.name} leave needs at least {leave_type.min_notice_days} day(s) notice."})
    if leave_type.max_consecutive_days and days > leave_type.max_consecutive_days:
        raise ValidationError({"detail": f"{leave_type.name} leave is limited to {leave_type.max_consecutive_days} working day(s) per request."})
    if check_document and leave_type.requires_document and not attachment:
        raise ValidationError({"attachment": f"{leave_type.name} leave requires a supporting document."})
    if attachment:
        _validate_attachment(attachment)
    if relief_officer and relief_officer.pk == user.pk:
        raise ValidationError({"relief_officer": "You cannot be your own relief officer."})

    if not leave_type.ignore_blackouts:
        blackout = (
            BlackoutPeriod.objects.filter(start_date__lte=end_date, end_date__gte=start_date)
            .filter(Q(department__isnull=True) | Q(department_id=user.department_id)).first()
        )
        if blackout:
            why = f": {blackout.reason}" if blackout.reason else ""
            raise ValidationError({"detail": f"Leave is not allowed during '{blackout.name}' ({blackout.start_date} to {blackout.end_date}){why}."})

    # Lock the employee row before checking overlaps so concurrent submissions
    # for different leave types cannot both pass the same overlap check.
    if lock:
        User.objects.select_for_update().get(pk=user.pk)
    clash = LeaveRequest.objects.filter(
        user=user, status__in=[Status.PENDING, Status.APPROVED], start_date__lte=end_date, end_date__gte=start_date
    ).exists()
    if clash:
        raise ValidationError({"detail": "These dates overlap with another pending or approved leave request."})

    approver = resolve_approver(user)
    if create_balance:
        balance = (_locked_balance if lock else _get_balance)(user, leave_type, start_date.year)
    else:
        balance = LeaveBalance.objects.filter(user=user, leave_type=leave_type, year=start_date.year).first()
        if balance is None:
            balance = LeaveBalance(user=user, leave_type=leave_type, year=start_date.year, entitled=leave_type.default_days)
    if balance.available < days:
        raise ValidationError(
            {"detail": f"Insufficient {leave_type.name} balance: {balance.available:g} day(s) available, {days:g} requested."}
        )
    return days, approver, balance


def preview_leave(*, user, leave_type, start_date, end_date, day_part=FULL, relief_officer=None):
    """Read-only dry run of submit_leave for live form feedback."""
    out = {"ok": True, "errors": [], "working_days": None, "approver": None, "balance_available": None, "balance_after": None}
    if end_date >= start_date:
        out["working_days"] = count_working_days(start_date, end_date, day_part if start_date == end_date else FULL)
    try:
        days, approver, balance = _check(
            user=user, leave_type=leave_type, start_date=start_date, end_date=end_date, day_part=day_part,
            relief_officer=relief_officer, check_document=False, create_balance=False,
        )
        out.update(approver=approver.display_name, balance_available=balance.available, balance_after=balance.available - days)
    except ValidationError as exc:
        out["ok"], out["errors"] = False, _flatten(exc.detail)
        try:
            out["approver"] = resolve_approver(user).display_name
        except ValidationError:
            pass
        if start_date.year == end_date.year:
            balance = LeaveBalance.objects.filter(user=user, leave_type=leave_type, year=start_date.year).first()
            out["balance_available"] = balance.available if balance else leave_type.default_days
    return out


@transaction.atomic
def submit_leave(*, user, leave_type, start_date, end_date, day_part=FULL, reason="", attachment=None, relief_officer=None):
    days, approver, balance = _check(
        user=user, leave_type=leave_type, start_date=start_date, end_date=end_date, day_part=day_part,
        attachment=attachment, relief_officer=relief_officer, lock=True,
    )
    req = LeaveRequest.objects.create(
        user=user, leave_type=leave_type, start_date=start_date, end_date=end_date, day_part=day_part,
        working_days=days, reason=reason or "", attachment=attachment or "", current_approver=approver,
        relief_officer=relief_officer,
    )
    balance.pending += days
    balance.save(update_fields=["pending"])
    _log(req, user, Action.SUBMITTED, reason)
    msg = f"{user.display_name} requested {days:g} day(s) of {leave_type.name} leave ({start_date} to {end_date})."
    notify(approver, "leave_submitted", msg, req)
    today = timezone.localdate()
    for d in Delegation.objects.filter(delegator=approver, is_active=True, start_date__lte=today, end_date__gte=today).select_related("delegate"):
        notify(d.delegate, "leave_submitted", f"(Delegated from {approver.display_name}) {msg}", req)
    if relief_officer:
        notify(relief_officer, "relief_request", f"{user.display_name} named you as relief officer ({start_date} to {end_date}).", req)
    return req


@transaction.atomic
def approve(req, actor, comment=""):
    req = _lock(req)
    
    # 1. Handle HR final approval for AWAITING_HR requests
    if req.status == Status.AWAITING_HR and actor.is_hr:
        balance = _locked_balance(req.user, req.leave_type, req.start_date.year)
        balance.pending -= req.working_days
        balance.used += req.working_days
        balance.save(update_fields=["pending", "used"])
        req.status, req.decided_by, req.decided_at = Status.APPROVED, actor, timezone.now()
        req.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
        _log(req, actor, Action.APPROVED, f"HR final approval: {comment}")
        notify(req.user, "leave_approved", 
               f"Your {req.leave_type.name} leave ({req.start_date} to {req.end_date}) was approved by HR.", req)
        return req

    # 2. HOD approval (must be pending)
    _require_pending_approver(req, actor)
    
    # 2a. Long leaves go to HR
    if req.working_days > HR_THRESHOLD_DAYS:
        req.status = Status.AWAITING_HR
        req.current_approver = None
        req.save(update_fields=["status", "current_approver", "updated_at"])
        _log(req, actor, Action.APPROVED, f"HOD approved. Sent to HR for final approval. {comment}")
        
        from accounts.models import Roles, User
        from django.db.models import Q
        hr_users = User.objects.filter(is_active=True).filter(
            Q(groups__name__in=[Roles.HR_MANAGER, Roles.ADMIN]) | Q(is_superuser=True)
        ).distinct()
        for hr in hr_users:
            notify(hr, "leave_awaiting_hr", 
                   f"{req.user.display_name}'s leave ({req.working_days} days) requires HR approval.", req)
        return req
    
    # 2b. Standard HOD approval (<= 14 days)
    balance = _locked_balance(req.user, req.leave_type, req.start_date.year)
    balance.pending -= req.working_days
    balance.used += req.working_days
    balance.save(update_fields=["pending", "used"])
    req.status, req.decided_by, req.decided_at = Status.APPROVED, actor, timezone.now()
    req.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    _log(req, actor, Action.APPROVED, _on_behalf(req, actor, comment))
    notify(req.user, "leave_approved", 
           f"Your {req.leave_type.name} leave ({req.start_date} to {req.end_date}) was approved.", req)
    return req

@transaction.atomic
def reject(req, actor, comment):
    if not (comment or "").strip():
        raise ValidationError({"comment": "A reason is required when rejecting a request."})
    req = _lock(req)

    # HR can reject an awaiting_hr request
    if req.status == Status.AWAITING_HR and actor.is_hr:
        # HR rejection
        balance = _locked_balance(req.user, req.leave_type, req.start_date.year)
        balance.pending -= req.working_days  # Release pending balance
        balance.save(update_fields=["pending"])
        req.status, req.decided_by, req.decided_at = Status.REJECTED, actor, timezone.now()
        req.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
        _log(req, actor, Action.REJECTED, f"HR rejected: {comment}")
        notify(req.user, "leave_rejected", f"Your {req.leave_type.name} leave was rejected by HR: {comment}", req)
        return req

    _require_pending_approver(req, actor)
    balance = _locked_balance(req.user, req.leave_type, req.start_date.year)
    balance.pending -= req.working_days
    balance.save(update_fields=["pending"])
    req.status, req.decided_by, req.decided_at = Status.REJECTED, actor, timezone.now()
    req.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    _log(req, actor, Action.REJECTED, _on_behalf(req, actor, comment))
    notify(req.user, "leave_rejected", f"Your {req.leave_type.name} leave ({req.start_date} to {req.end_date}) was rejected: {comment}", req)
    return req


@transaction.atomic
def cancel(req, actor, comment=""):
    req = _lock(req)
    if req.user_id != actor.pk:
        raise PermissionDenied("Only the requester can cancel a request.")
    balance = _locked_balance(req.user, req.leave_type, req.start_date.year)
    if req.status == Status.PENDING:
        balance.pending -= req.working_days
    elif req.status == Status.APPROVED and req.start_date > timezone.localdate():
        balance.used -= req.working_days
    else:
        raise ValidationError({"detail": "This request can no longer be cancelled."})
    balance.save(update_fields=["pending", "used"])
    approver = req.current_approver
    req.status = Status.CANCELLED
    req.save(update_fields=["status", "updated_at"])
    _log(req, actor, Action.CANCELLED, comment)
    if approver:
        notify(approver, "leave_cancelled", f"{req.user.display_name} cancelled their leave request ({req.start_date} to {req.end_date}).", req)
    return req


@transaction.atomic
def hr_review(req, actor, note=""):
    if not actor.is_hr:
        raise PermissionDenied("Only HR can review leave requests.")
    req = _lock(req)
    if req.status not in (Status.APPROVED, Status.REJECTED):
        raise ValidationError({"detail": "Only approved or rejected requests can be reviewed."})
    if req.hr_reviewed_at:
        raise ValidationError({"detail": "This request has already been reviewed."})
    req.hr_reviewed_by, req.hr_reviewed_at, req.hr_note = actor, timezone.now(), note or ""
    req.save(update_fields=["hr_reviewed_by", "hr_reviewed_at", "hr_note", "updated_at"])
    _log(req, actor, Action.HR_REVIEWED, note)
    return req


def _reassign(req, actor, new_approver, comment):
    previous = req.current_approver
    req.current_approver = new_approver
    req.save(update_fields=["current_approver", "updated_at"])
    _log(req, actor, Action.REASSIGNED, comment or f"Reassigned to {new_approver.display_name}")
    notify(new_approver, "leave_assigned", f"{req.user.display_name}'s leave request ({req.start_date} to {req.end_date}) was assigned to you.", req)
    if previous and previous.pk != new_approver.pk:
        notify(previous, "leave_unassigned", f"{req.user.display_name}'s leave request was reassigned to {new_approver.display_name}.", req)


@transaction.atomic
def reassign_approver(req, actor, new_approver, comment=""):
    """HR hands a pending request to someone else (approver away, left the institution, etc.)."""
    if not actor.is_hr:
        raise PermissionDenied("Only HR can reassign approvers.")
    req = _lock(req)
    if req.status != Status.PENDING:
        raise ValidationError({"detail": "Only pending requests can be reassigned."})
    if not new_approver.is_active or new_approver.pk == req.user_id:
        raise ValidationError({"approver": "Choose an active user other than the requester."})
    _reassign(req, actor, new_approver, comment)
    return req


@transaction.atomic
def escalate_stale(days=7):
    """
    Requests pending longer than `days` move up to the department head. If that is not possible
    (already with the head, or no head) HR is alerted once. Returns (escalated, alerted).
    """
    cutoff = timezone.now() - dt.timedelta(days=days)
    escalated = alerted = 0
    hr_users = list(
        User.objects.filter(is_active=True).filter(Q(groups__name__in=[Roles.HR_MANAGER, Roles.ADMIN]) | Q(is_superuser=True)).distinct()
    )
    stale = LeaveRequest.objects.filter(status=Status.PENDING, created_at__lte=cutoff).select_related("user", "user__department", "current_approver")
    for req in stale:
        head = req.user.department.head if req.user.department_id else None
        if head and head.is_active and head.pk not in (req.user_id, req.current_approver_id):
            _reassign(req, None, head, f"Auto-escalated after {days} day(s) without a decision")
            escalated += 1
            continue
        for hr in hr_users:
            if not Notification.objects.filter(user=hr, kind="leave_escalated", leave_request=req).exists():
                notify(hr, "leave_escalated", f"{req.user.display_name}'s leave request has waited over {days} day(s) with no decision.", req)
                alerted += 1
    return escalated, alerted
