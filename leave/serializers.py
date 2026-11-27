from rest_framework import serializers

from accounts.models import User

from . import services
from .models import (
    BlackoutPeriod, Delegation, Holiday, LeaveAction, LeaveBalance, LeaveRequest, LeaveType, Notification,
)

Status = LeaveRequest.Status
DAYS = dict(max_digits=6, decimal_places=1)


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = [
            "id", "name", "default_days", "requires_document", "is_paid", "carry_over_cap",
            "min_notice_days", "max_consecutive_days", "ignore_blackouts", "is_active",
        ]


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ["id", "date", "name"]


class BlackoutSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)

    class Meta:
        model = BlackoutPeriod
        fields = ["id", "name", "start_date", "end_date", "department", "department_name", "reason"]

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date cannot be before start date."})
        return attrs


class DelegationSerializer(serializers.ModelSerializer):
    delegator_name = serializers.CharField(source="delegator.display_name", read_only=True)
    delegate_name = serializers.CharField(source="delegate.display_name", read_only=True)

    class Meta:
        model = Delegation
        fields = ["id", "delegator", "delegator_name", "delegate", "delegate_name", "start_date", "end_date", "note", "created_at"]
        read_only_fields = ["id", "delegator", "created_at"]

    def validate_delegate(self, value):
        if not value.is_active:
            raise serializers.ValidationError("This user is not active.")
        if value == self.context["request"].user:
            raise serializers.ValidationError("You cannot delegate to yourself.")
        return value

    def validate(self, attrs):
        if attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError({"end_date": "End date cannot be before start date."})
        from django.utils import timezone
        if attrs["end_date"] < timezone.localdate():
            raise serializers.ValidationError({"end_date": "End date is in the past."})
        return attrs


class LeaveBalanceSerializer(serializers.ModelSerializer):
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    available = serializers.DecimalField(read_only=True, **DAYS)

    class Meta:
        model = LeaveBalance
        fields = ["id", "leave_type", "leave_type_name", "year", "entitled", "used", "pending", "available"]


class LeaveActionSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.display_name", read_only=True, default=None)

    class Meta:
        model = LeaveAction
        fields = ["id", "action", "actor", "actor_name", "comment", "created_at"]


class ActivitySerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.display_name", read_only=True, default="System")
    request_id = serializers.IntegerField(source="leave_request_id", read_only=True)
    requester_name = serializers.CharField(source="leave_request.user.display_name", read_only=True)
    leave_type_name = serializers.CharField(source="leave_request.leave_type.name", read_only=True)
    start_date = serializers.DateField(source="leave_request.start_date", read_only=True)
    end_date = serializers.DateField(source="leave_request.end_date", read_only=True)

    class Meta:
        model = LeaveAction
        fields = ["id", "action", "actor_name", "comment", "created_at", "request_id", "requester_name",
                  "leave_type_name", "start_date", "end_date"]


class LeaveRequestSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.display_name", read_only=True)
    department = serializers.CharField(source="user.department.name", read_only=True, default=None)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    approver_name = serializers.CharField(source="current_approver.display_name", read_only=True, default=None)
    relief_officer_name = serializers.CharField(source="relief_officer.display_name", read_only=True, default=None)
    hr_reviewed_by_name = serializers.CharField(source="hr_reviewed_by.display_name", read_only=True, default=None)
    has_attachment = serializers.SerializerMethodField()
    overlap_count = serializers.SerializerMethodField()

    class Meta:
        model = LeaveRequest
        fields = [
            "id", "user", "user_name", "department", "leave_type", "leave_type_name",
            "start_date", "end_date", "day_part", "working_days", "reason", "status", "has_attachment",
            "current_approver", "approver_name", "relief_officer", "relief_officer_name",
            "decided_by", "decided_at", "hr_reviewed_by", "hr_reviewed_by_name", "hr_reviewed_at", "hr_note",
            "created_at", "updated_at", "overlap_count",
        ]
        read_only_fields = fields

    def get_has_attachment(self, obj):
        return bool(obj.attachment)

    def get_overlap_count(self, obj):
        return getattr(obj, "overlap_count", None)  # only annotated on the approval queue


class LeaveRequestDetailSerializer(LeaveRequestSerializer):
    actions = LeaveActionSerializer(many=True, read_only=True)
    team_overlap = serializers.SerializerMethodField()
    requester_balance = serializers.SerializerMethodField()
    can_decide = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()

    class Meta(LeaveRequestSerializer.Meta):
        fields = LeaveRequestSerializer.Meta.fields + ["actions", "team_overlap", "requester_balance", "can_decide", "can_cancel"]
        read_only_fields = fields

    def _viewer(self):
        return self.context["request"].user

    def get_team_overlap(self, obj):
        """Colleagues from the same department who are away on the same dates (shown to approvers/HR, not the requester)."""
        if obj.user_id == self._viewer().pk or not obj.user.department_id:
            return []
        qs = LeaveRequest.objects.filter(
            user__department_id=obj.user.department_id, status__in=[Status.PENDING, Status.APPROVED],
            start_date__lte=obj.end_date, end_date__gte=obj.start_date,
        ).exclude(user_id=obj.user_id).select_related("user")
        return [{"request": r.pk, "user_name": r.user.display_name, "start_date": r.start_date, "end_date": r.end_date, "status": r.status} for r in qs]

    def get_requester_balance(self, obj):
        b = LeaveBalance.objects.filter(user=obj.user, leave_type=obj.leave_type, year=obj.start_date.year).first()
        if not b:
            return None
        return {"entitled": b.entitled, "used": b.used, "pending": b.pending, "available": b.available}

    def get_can_decide(self, obj):
        return obj.status == Status.PENDING and services.can_decide(obj, self._viewer())

    def get_can_cancel(self, obj):
        from django.utils import timezone
        if obj.user_id != self._viewer().pk:
            return False
        return obj.status == Status.PENDING or (obj.status == Status.APPROVED and obj.start_date > timezone.localdate())


class LeaveRequestCreateSerializer(serializers.Serializer):
    leave_type = serializers.PrimaryKeyRelatedField(queryset=LeaveType.objects.filter(is_active=True))
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    day_part = serializers.ChoiceField(choices=LeaveRequest.DayPart.choices, required=False, default="full")
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    attachment = serializers.FileField(required=False, allow_null=True)
    relief_officer = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), required=False, allow_null=True
    )


class CommentSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class ReassignSerializer(serializers.Serializer):
    approver = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True))
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "kind", "message", "leave_request", "read_at", "created_at"]
