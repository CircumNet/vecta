from django.conf import settings
from django.db import models
from django.db.models import F, Q

User = settings.AUTH_USER_MODEL
DAYS = dict(max_digits=5, decimal_places=1)


class LeaveType(models.Model):
    name = models.CharField(max_length=80, unique=True)
    default_days = models.PositiveIntegerField(help_text="Yearly entitlement in working days")
    requires_document = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=True)
    carry_over_cap = models.PositiveIntegerField(default=0, help_text="Max unused days carried into next year")
    min_notice_days = models.PositiveIntegerField(default=0, help_text="Calendar days of notice required before the start date")
    max_consecutive_days = models.PositiveIntegerField(default=0, help_text="Max working days in one request (0 = no limit)")
    ignore_blackouts = models.BooleanField(default=False, help_text="Allow this type during blackout periods (e.g. sick leave)")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class LeaveBalance(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="leave_balances")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="balances")
    year = models.PositiveIntegerField()
    entitled = models.DecimalField(**DAYS)
    used = models.DecimalField(default=0, **DAYS)
    pending = models.DecimalField(default=0, **DAYS)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "leave_type", "year"], name="uniq_balance")]
        ordering = ["year", "leave_type__name"]

    @property
    def available(self):
        return self.entitled - self.used - self.pending

    def __str__(self):
        return f"{self.user} {self.leave_type} {self.year}: {self.available} left"


class Holiday(models.Model):
    date = models.DateField(unique=True)
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date} {self.name}"


class BlackoutPeriod(models.Model):
    """Dates when leave is not allowed (exams, audits, year-end close...). Empty department = whole institution."""

    name = models.CharField(max_length=120)
    start_date = models.DateField()
    end_date = models.DateField()
    department = models.ForeignKey("accounts.Department", null=True, blank=True, on_delete=models.CASCADE, related_name="blackouts")
    reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["start_date"]
        constraints = [models.CheckConstraint(condition=Q(end_date__gte=F("start_date")), name="blackout_end_after_start")]

    def __str__(self):
        return f"{self.name} {self.start_date}→{self.end_date}"


class Delegation(models.Model):
    """An approver hands their approval queue to someone else for a period (out of office)."""

    delegator = models.ForeignKey(User, on_delete=models.CASCADE, related_name="delegations_given")
    delegate = models.ForeignKey(User, on_delete=models.CASCADE, related_name="delegations_received")
    start_date = models.DateField()
    end_date = models.DateField()
    note = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]
        constraints = [models.CheckConstraint(condition=Q(end_date__gte=F("start_date")), name="delegation_end_after_start")]


class LeaveRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        AWAITING_HR = "awaiting_hr" 
        REJECTED = "rejected"
        CANCELLED = "cancelled"

    class DayPart(models.TextChoices):
        FULL = "full"
        MORNING = "morning"
        AFTERNOON = "afternoon"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="requests")
    start_date = models.DateField()
    end_date = models.DateField()
    day_part = models.CharField(max_length=10, choices=DayPart.choices, default=DayPart.FULL)
    working_days = models.DecimalField(**DAYS)
    reason = models.TextField(blank=True)
    attachment = models.FileField(upload_to="leave_attachments/%Y/%m/", blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)

    current_approver = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="approvals_assigned")
    relief_officer = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="relief_for")

    decided_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)

    # HR review happens AFTER the approver's decision; it does not change the decision.
    hr_reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    hr_reviewed_at = models.DateTimeField(null=True, blank=True)
    hr_note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "start_date"]),
            models.Index(fields=["current_approver", "status"]),
        ]
        constraints = [models.CheckConstraint(condition=Q(end_date__gte=F("start_date")), name="leave_end_after_start")]

    def __str__(self):
        return f"{self.user} {self.leave_type} {self.start_date}→{self.end_date} [{self.status}]"


class LeaveAction(models.Model):
    """Append-only audit trail. Never edited or deleted by application code."""

    class Action(models.TextChoices):
        SUBMITTED = "submitted"
        APPROVED = "approved"
        REJECTED = "rejected"
        CANCELLED = "cancelled"
        REASSIGNED = "reassigned"
        HR_REVIEWED = "hr_reviewed"

    leave_request = models.ForeignKey(LeaveRequest, on_delete=models.CASCADE, related_name="actions")
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=12, choices=Action.choices)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=30)
    message = models.CharField(max_length=300)
    leave_request = models.ForeignKey(LeaveRequest, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "read_at"])]

