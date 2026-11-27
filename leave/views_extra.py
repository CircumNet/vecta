"""Dashboard, team calendar, directory, delegation, audit feed and iCal export."""
import datetime as dt

from django.db.models import F, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics, mixins, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsHR

from . import services
from .models import BlackoutPeriod, Delegation, Holiday, LeaveAction, LeaveRequest
from .serializers import ActivitySerializer, DelegationSerializer, LeaveBalanceSerializer, LeaveRequestSerializer
from .views import _date_param

Status = LeaveRequest.Status
OPEN = [Status.PENDING, Status.APPROVED]


class DashboardView(APIView):
    """One round trip for the home screen. Sections appear according to the viewer's role."""

    def get(self, request):
        u, today = request.user, timezone.localdate()
        mine = LeaveRequest.objects.filter(user=u)
        upcoming = mine.filter(status__in=OPEN, end_date__gte=today).select_related("user", "leave_type").order_by("start_date")[:5]
        delegators = services.active_delegators(u)
        queue = (
            LeaveRequest.objects.filter(status=Status.PENDING).exclude(user=u)
            .filter(Q(current_approver=u) | Q(current_approver__in=delegators))
        )
        data = {
            "me": {
                "balances": LeaveBalanceSerializer(services.ensure_balances(u, today.year), many=True).data,
                "upcoming": LeaveRequestSerializer(upcoming, many=True).data,
                "pending": mine.filter(status=Status.PENDING).count(),
            },
            "approver": {"pending": queue.count(), "as_delegate": bool(delegators)},
            "away_today": [
                {"user": r.user_id, "name": r.user.display_name, "leave_type": r.leave_type.name, "until": r.end_date}
                for r in services.on_leave_today(u)
            ],
        }
        if u.is_hr:
            year_start = dt.date(today.year, 1, 1)
            approved = LeaveRequest.objects.filter(status=Status.APPROVED, start_date__gte=year_start, start_date__lte=dt.date(today.year, 12, 31))
            agg = Sum("working_days")
            data["hr"] = {
                "awaiting_review": LeaveRequest.objects.filter(status__in=[Status.APPROVED, Status.REJECTED], hr_reviewed_at__isnull=True).count(),
                "pending_total": LeaveRequest.objects.filter(status=Status.PENDING).count(),
                "stale_pending": LeaveRequest.objects.filter(status=Status.PENDING, created_at__lte=timezone.now() - dt.timedelta(days=7)).count(),
                "on_leave_today": services.on_leave_today(u).count(),
                "headcount": User.objects.filter(is_active=True).count(),
                "needs_setup": User.objects.filter(is_active=True, is_superuser=False, department__isnull=True).exclude(groups__name__in=["hr_manager", "admin"]).count(),
                "year": today.year,
                "monthly": [{"month": m["month"], "days": m["days"] or 0}
                            for m in approved.annotate(month=TruncMonth("start_date")).values("month").annotate(days=agg).order_by("month")],
                "by_department": [{"name": r["name"] or "Unassigned", "days": r["days"] or 0}
                                  for r in approved.values(name=F("user__department__name")).annotate(days=agg).order_by("-days")],
                "by_type": [{"name": r["name"], "days": r["days"] or 0}
                            for r in approved.values(name=F("leave_type__name")).annotate(days=agg).order_by("-days")],
            }
        return Response(data)


class CalendarView(APIView):
    """
    GET /api/calendar/?from=&to=[&department=]
    Staff see only their own requests. Department heads see their department.
    HR sees institution-wide leave. Calendar access is determined by department membership and role.
    """

    def get(self, request):
        p = request.query_params
        start, end = _date_param(p, "from", True), _date_param(p, "to", True)
        if end < start or (end - start).days > 100:
            raise ValidationError({"to": "Choose a range of at most 100 days."})
        
        u, hr = request.user, request.user.is_hr
        qs = LeaveRequest.objects.filter(start_date__lte=end, end_date__gte=start).select_related(
            "user", "user__department", "leave_type"
        )
        
        headed_department_ids = [] if hr else list(u.headed_departments.values_list("pk", flat=True))
        
        if hr:
            qs = qs.filter(status__in=OPEN)
            if p.get("department"):
                qs = qs.filter(user__department_id=p["department"])
        else:
            if headed_department_ids:
                # HOD sees everyone in their department(s)
                qs = qs.filter(user__department_id__in=headed_department_ids, status__in=OPEN)
            else:
                # Staff see ONLY their own
                qs = qs.filter(user=u, status__in=OPEN)
                
        events = []
        for r in qs.order_by("start_date", "user__last_name"):
            # PRIVACY LOGIC: Only show leave_type if the viewer is HR, the owner, or the HOD
            detailed = hr or r.user_id == u.pk or r.user.department_id in headed_department_ids
            
            events.append({
                "id": r.pk, 
                "user": r.user_id, 
                "name": r.user.display_name,
                "department": r.user.department.name if r.user.department else None,
                "start_date": r.start_date, 
                "end_date": r.end_date, 
                "working_days": r.working_days,
                "status": r.status, 
                "mine": r.user_id == u.pk, 
                "day_part": r.day_part,
                # Hide leave type from staff viewing colleagues
                "leave_type": r.leave_type.name if detailed else "Leave", 
                "detailed": bool(detailed),
            })
            
        blackouts = BlackoutPeriod.objects.filter(start_date__lte=end, end_date__gte=start).select_related("department")
        if not hr:
            blackouts = blackouts.filter(Q(department__isnull=True) | Q(department_id=u.department_id))
            
        return Response({
            "events": events,
            "holidays": [{"date": h.date, "name": h.name} for h in Holiday.objects.filter(date__range=(start, end))],
            "blackouts": [{"name": b.name, "start_date": b.start_date, "end_date": b.end_date, "reason": b.reason,
                           "department_name": b.department.name if b.department else None} for b in blackouts],
        })


class DirectoryView(APIView):
    """Minimal colleague lookup for pickers (relief officer, delegate). Same department by default."""

    def get(self, request):
        u = request.user
        qs = User.objects.filter(is_active=True).exclude(pk=u.pk).select_related("department")
        # Only HR may search institution-wide or request the full directory.
        if not u.is_hr:
            qs = qs.filter(department_id=u.department_id) if u.department_id else qs.none()
        s = request.query_params.get("search")
        if s:
            qs = qs.filter(Q(first_name__icontains=s) | Q(last_name__icontains=s) | Q(username__icontains=s))
        return Response([
            {"id": x.pk, "full_name": x.display_name, "job_title": x.job_title,
             "department_name": x.department.name if x.department else None}
            for x in qs.order_by("first_name", "last_name", "username")[:100]
        ])


class DelegationViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = DelegationSerializer
    pagination_class = None

    def get_queryset(self):
        u = self.request.user
        return Delegation.objects.filter(Q(delegator=u) | Q(delegate=u), is_active=True).select_related("delegator", "delegate")

    def perform_create(self, serializer):
        if not (set(self.request.user.roles) & services.APPROVER_ROLES):
            raise PermissionDenied("Only approvers can delegate their queue.")
        d = serializer.save(delegator=self.request.user)
        services.notify(
            d.delegate, "delegation",
            f"{d.delegator.display_name} delegated their leave approvals to you ({d.start_date} to {d.end_date}).",
        )

    def destroy(self, request, *args, **kwargs):
        d = self.get_object()
        if d.delegator_id != request.user.pk and not request.user.is_hr:
            raise PermissionDenied("Only the person who delegated can revoke it.")
        d.is_active = False
        d.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActivityView(generics.ListAPIView):
    """HR audit feed of every workflow action."""

    permission_classes = [IsHR]
    serializer_class = ActivitySerializer

    def get_queryset(self):
        qs = LeaveAction.objects.select_related("actor", "leave_request__user", "leave_request__leave_type").order_by("-created_at", "-id")
        if self.request.query_params.get("action"):
            qs = qs.filter(action=self.request.query_params["action"])
        return qs


class MyCalendarICSView(APIView):
    """Download my approved/pending leave as an .ics file for Google/Outlook/Apple calendar."""

    def get(self, request):
        today = timezone.localdate()
        rows = LeaveRequest.objects.filter(
            user=request.user, status__in=OPEN, end_date__gte=today - dt.timedelta(days=30)
        ).select_related("leave_type")
        stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Vecta//EN", "CALSCALE:GREGORIAN"]
        for r in rows:
            tag = "" if r.status == Status.APPROVED else " (pending)"
            lines += [
                "BEGIN:VEVENT", f"UID:leave-{r.pk}@vecta", f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{r.start_date:%Y%m%d}",
                f"DTEND;VALUE=DATE:{r.end_date + dt.timedelta(days=1):%Y%m%d}",
                f"SUMMARY:{r.leave_type.name} leave{tag}", "TRANSP:OPAQUE", "END:VEVENT",
            ]
        lines.append("END:VCALENDAR")
        resp = HttpResponse("\r\n".join(lines) + "\r\n", content_type="text/calendar")
        resp["Content-Disposition"] = 'attachment; filename="my-leave.ics"'
        return resp
