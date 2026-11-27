from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
import secrets
from datetime import timedelta
from django.utils import timezone

class Roles:
    """
    Stored roles: staff, hr_manager, admin.
    Derived roles:
      department_head -> is the head of a department.
    """

    STAFF = "staff"
    HR_MANAGER = "hr_manager"
    ADMIN = "admin"
    DEPARTMENT_HEAD = "department_head"
    STORED = (STAFF, HR_MANAGER, ADMIN)
    ASSIGNABLE = (HR_MANAGER, ADMIN)


class Department(models.Model):
    name = models.CharField(max_length=120, unique=True)
    
    UNIT_CHOICES = [
        ("academic", "Academic"),
        ("non_academic", "Non-academic"),
    ]
    unit = models.CharField(
        max_length=20,
        choices=UNIT_CHOICES,
        default="academic",
    )
    
    head = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="headed_departments"
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    staff_id = models.CharField(max_length=30, unique=True, null=True, blank=True)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="members")
    job_title = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    must_change_password = models.BooleanField(default=True)
    email_notifications = models.BooleanField(default=True)
    email_verified = models.BooleanField(default=False)
    # Self-registered accounts stay inactive until the emailed code is confirmed.
    signup_pending = models.BooleanField(default=False)
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(Lower("email"), condition=~models.Q(email=""), name="uniq_user_email_ci"),
        ]

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def is_admin(self):
        return self.is_superuser or self.groups.filter(name=Roles.ADMIN).exists()

    @property
    def is_hr(self):
        return self.is_admin or self.groups.filter(name=Roles.HR_MANAGER).exists()

    @property
    def roles(self):
        names = set(self.groups.values_list("name", flat=True))
        if self.is_superuser:
            names.add(Roles.ADMIN)
        if self.headed_departments.exists():
            names.add(Roles.DEPARTMENT_HEAD)
        return sorted(names)

    def __str__(self):
        return self.display_name


class EmailCode(models.Model):
    """A one-time 6-digit code sent by email (hashed at rest, expires, limited attempts)."""

    class Purpose(models.TextChoices):
        REGISTER = "register"
        RESET = "reset"
        EMAIL_CHANGE = "email_change"

    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    email = models.EmailField()  # the address the code was sent to (lower-case)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    code_hash = models.CharField(max_length=64)
    token_hash = models.CharField(max_length=64, blank=True)  # set once the code is verified (password reset)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["purpose", "email", "created_at"]), models.Index(fields=["token_hash"])]
        

class OAuthIdentity(models.Model):
    """A Google / Microsoft account linked to a user."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="identities")
    provider = models.CharField(max_length=20)
    subject = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "subject"], name="uniq_oauth_subject")]


class OAuthFlow(models.Model):
    """State for one in-flight OAuth round trip (CSRF state + PKCE verifier + one-time exchange code)."""

    state = models.CharField(max_length=64, unique=True)
    provider = models.CharField(max_length=20)
    mode = models.CharField(max_length=10)  # login | link
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    code_verifier = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    exchange_hash = models.CharField(max_length=64, blank=True)
    exchange_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    exchange_expires = models.DateTimeField(null=True, blank=True)


class RoleRequest(models.Model):
    class RequestedRole(models.TextChoices):
        HOD = "department_head", "Head of Department"
        HR_MANAGER = "hr_manager", "HR Manager"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="role_requests"
    )
    requested_role = models.CharField(
        max_length=30,
        choices=RequestedRole.choices
    )
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="role_requests"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_role_requests"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.get_requested_role_display()} ({self.status})"

class HRInvitation(models.Model):
    token = models.CharField(max_length=64, unique=True)
    email = models.EmailField(help_text="The email address this invitation is locked to.")
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=3)
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        return self.used_at is None and self.expires_at > timezone.now()