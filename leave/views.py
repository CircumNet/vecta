import csv
import datetime as dt
import os

from django.db.models import Count, F, IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.db.models.functions import TruncMonth
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsActiveAndPasswordSet, IsHR, ReadAnyWriteHR

from . import services
from .models import BlackoutPeriod, Holiday, LeaveRequest, LeaveType, Notification
from .permissions import CanViewLeaveRequest
from .serializers import (
    BlackoutSerializer, CommentSerializer, HolidaySerializer, LeaveBalanceSerializer, LeaveRequestCreateSerializer,
    LeaveRequestDetailSerializer, LeaveRequestSerializer, LeaveTypeSerializer, NotificationSerializer, ReassignSerializer,
)

Status = LeaveRequest.Status


def _date_param(params, key, required=False):
    raw = params.get(key)
    if not raw:
        if required:
            raise ValidationError({key: "This query parameter is required (YYYY-MM-DD)."})
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        raise ValidationError({key: "Use the format YYYY-MM-DD."})


class LeaveTypeViewSet(viewsets.ModelViewSet):
    queryset = LeaveType.objects.all()
    serializer_class = LeaveTypeSerializer
    permission_classes = [ReadAnyWriteHR]
    pagination_class = None

    def perform_destroy(self, instance):
        # Requests and balances reference leave types, so "delete" retires the type instead.
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class HolidayViewSet(viewsets.ModelViewSet):
    queryset = Holiday.objects.all()
    serializer_class = HolidaySerializer
    permission_classes = [ReadAnyWriteHR]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("year"):
            qs = qs.filter(date__year=self.request.query_params["year"])
        return qs


class BlackoutViewSet(viewsets.ModelViewSet):
    queryset = BlackoutPeriod.objects.select_related("department")
    serializer_class = BlackoutSerializer
    permission_classes = [ReadAnyWriteHR]
    pagination_class = None


def _overlap_subquery():
    """Per-row count of colleagues (same department) away on the same dates."""
    return Coalesce(
        Subquery(
            LeaveRequest.objects.filter(
                user__department_id=OuterRef("user__department_id"), status__in=[Status.PENDING, Status.APPROVED],
                start_date__lte=OuterRef("end_date"), end_date__gte=OuterRef("start_date"),
            ).exclude(user_id=OuterRef("user_id")).order_by().values("user__department_id")
            .annotate(c=Count("id")).values("c"),
            output_field=IntegerField(),
        ),
        0,
    )


class MyBalancesView(APIView):
    def get(self, request):
        year = int(request.query_params.get("year") or timezone.localdate().year)
        return Response(LeaveBalanceSerializer(services.ensure_balances(request.user, year), many=True).data)


class LeaveRequestViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    serializer_class = LeaveRequestSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    permission_classes = [CanViewLeaveRequest]
    queryset = LeaveRequest.objects.select_related(
        "user", "user__department", "leave_type", "current_approver", "relief_officer", "hr_reviewed_by"
    ).prefetch_related("actions__actor")

    def get_serializer_class(self):
        if self.action in ("list", "mine", "pending_approval", "decided"):
            return LeaveRequestSerializer
        return LeaveRequestDetailSerializer

    def get_permissions(self):
        if self.action == "list":
            return [IsHR()]
        return super().get_permissions()

    # ---- helpers
    def _page(self, qs):
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def _fresh(self, obj):
        return self.get_serializer(self.get_queryset().get(pk=obj.pk)).data

    def _filtered(self, qs):
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("department"):
            qs = qs.filter(user__department_id=p["department"])
        if p.get("leave_type"):
            qs = qs.filter(leave_type_id=p["leave_type"])
        if p.get("user"):
            qs = qs.filter(user_id=p["user"])
        start, end = _date_param(p, "from"), _date_param(p, "to")
        if start:
            qs = qs.filter(end_date__gte=start)
        if end:
            qs = qs.filter(start_date__lte=end)
        if p.get("reviewed") in ("true", "1"):
            qs = qs.filter(hr_reviewed_at__isnull=False)
        elif p.get("reviewed") in ("false", "0"):
            qs = qs.filter(hr_reviewed_at__isnull=True, status__in=[Status.APPROVED, Status.REJECTED])
        return qs

    def list(self, request, *args, **kwargs):
        return self._page(self._filtered(self.get_queryset()))

    def create(self, request, *args, **kwargs):
        ser = LeaveRequestCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = services.submit_leave(user=request.user, **ser.validated_data)
        return Response(self._fresh(obj), status=status.HTTP_201_CREATED)

    # ---- scoped lists
    @action(detail=False, methods=["get"])
    def mine(self, request):
        qs = self.get_queryset().filter(user=request.user)
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return self._page(qs)

    @action(detail=False, methods=["get"], url_path="pending-approval")
    def pending_approval(self, request):
        """My queue, plus anything handed to me through an active delegation."""
        delegators = services.active_delegators(request.user)
        # Include awaiting_hr for HR users
        if request.user.is_hr:
            qs = self.get_queryset().filter(
                Q(status=Status.PENDING) | Q(status=Status.AWAITING_HR)
            ).exclude(user=request.user)
        else:
            qs = (
                self.get_queryset().filter(status=Status.PENDING)
                .filter(Q(current_approver=request.user) | Q(current_approver__in=delegators))
                .exclude(user=request.user)
            )
        qs = qs.annotate(overlap_count=_overlap_subquery()).order_by("start_date")
        return self._page(qs)

    @action(detail=False, methods=["get"])
    def decided(self, request):
        """Requests I have approved or rejected."""
        return self._page(self.get_queryset().filter(decided_by=request.user).order_by("-decided_at"))

    @action(detail=False, methods=["post"])
    def preview(self, request):
        """Dry-run the submission rules for live form feedback. Nothing is saved."""
        ser = LeaveRequestCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        return Response(services.preview_leave(
            user=request.user, leave_type=d["leave_type"], start_date=d["start_date"], end_date=d["end_date"],
            day_part=d.get("day_part", "full"), relief_officer=d.get("relief_officer"),
        ))

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        ser = CommentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(self._fresh(services.approve(self.get_object(), request.user, ser.validated_data["comment"])))

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        ser = CommentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(self._fresh(services.reject(self.get_object(), request.user, ser.validated_data["comment"])))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        ser = CommentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(self._fresh(services.cancel(self.get_object(), request.user, ser.validated_data["comment"])))

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """HR review of an approved/rejected request (adds a note; does not change the decision)."""
        ser = CommentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(self._fresh(services.hr_review(self.get_object(), request.user, ser.validated_data["comment"])))

    @action(detail=True, methods=["post"])
    def reassign(self, request, pk=None):
        ser = ReassignSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = services.reassign_approver(
            self.get_object(), request.user, ser.validated_data["approver"], ser.validated_data["comment"]
        )
        return Response(self._fresh(obj))

    @action(detail=True, methods=["get"])
    def attachment(self, request, pk=None):
        obj = self.get_object()
        if not obj.attachment:
            raise NotFound("No attachment on this request.")
        return FileResponse(obj.attachment.open("rb"), as_attachment=True, filename=os.path.basename(obj.attachment.name))


class NotificationListView(APIView):
    def get(self, request):
        qs = Notification.objects.filter(user=request.user)
        if request.query_params.get("unread") in ("true", "1"):
            qs = qs.filter(read_at__isnull=True)
        return Response(NotificationSerializer(qs[:100], many=True).data)


class NotificationMarkReadView(APIView):
    def post(self, request):
        qs = Notification.objects.filter(user=request.user, read_at__isnull=True)
        ids = request.data.get("ids")
        if ids:
            qs = qs.filter(pk__in=ids)
        return Response({"marked": qs.update(read_at=timezone.now())})


# ------------------------------------------------------------------ reports
class LeaveReportView(APIView):
    """
    GET /api/reports/leave/?from=YYYY-MM-DD&to=YYYY-MM-DD[&department=ID][&status=approved]
    Add &export=csv for a download. (Not `format=`: DRF reserves that parameter.)
    Requests overlapping the range are included; their working_days are counted in full.
    """

    permission_classes = [IsHR]

    def get(self, request):
        p = request.query_params
        start, end = _date_param(p, "from", True), _date_param(p, "to", True)
        if end < start:
            raise ValidationError({"to": "'to' cannot be before 'from'."})
        qs = LeaveRequest.objects.filter(start_date__lte=end, end_date__gte=start).select_related(
            "user", "user__department", "leave_type"
        )
        if p.get("department"):
            qs = qs.filter(user__department_id=p["department"])
        if p.get("status"):
            qs = qs.filter(status=p["status"])

        if p.get("export") == "csv":
            resp = HttpResponse(content_type="text/csv")
            resp["Content-Disposition"] = f'attachment; filename="leave_report_{start}_{end}.csv"'
            w = csv.writer(resp)
            w.writerow(["Staff ID", "Name", "Department", "Leave type", "Start", "End", "Working days", "Status",
                        "Decided by", "Decided at", "HR reviewed", "HR note"])
            for r in qs.order_by("user__department__name", "user__last_name", "start_date"):
                w.writerow([
                    r.user.staff_id or "", r.user.display_name, r.user.department.name if r.user.department else "",
                    r.leave_type.name, r.start_date, r.end_date, r.working_days, r.status,
                    r.decided_by.display_name if r.decided_by else "", r.decided_at or "",
                    "yes" if r.hr_reviewed_at else "no", r.hr_note,
                ])
            return resp

        agg = dict(requests=Count("id"), days=Sum("working_days"))
        return Response({
            "range": {"from": start, "to": end},
            "totals": qs.aggregate(**agg),
            "by_status": list(qs.values("status").annotate(**agg).order_by("status")),
            "by_leave_type": list(qs.values(name=F("leave_type__name")).annotate(**agg).order_by("name")),
            "by_department": list(qs.values(name=F("user__department__name")).annotate(**agg).order_by("name")),
            "by_month": list(qs.annotate(month=TruncMonth("start_date")).values("month").annotate(**agg).order_by("month")),
            "by_staff": list(
                qs.values("user_id", name=F("user__username")).annotate(**agg).order_by("-days")[:50]
            ),
            "awaiting_hr_review": qs.filter(status__in=[Status.APPROVED, Status.REJECTED], hr_reviewed_at__isnull=True).count(),
        })


class OnLeaveTodayView(APIView):
    """HR sees everyone on approved leave today; department heads see their own people."""

    def get(self, request):
        return Response([
            {"user": r.user_id, "name": r.user.display_name,
             "department": r.user.department.name if r.user.department else None,
             "leave_type": r.leave_type.name, "until": r.end_date}
            for r in services.on_leave_today(request.user)
        ])
