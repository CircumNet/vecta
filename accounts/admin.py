from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Department, User, OAuthIdentity, RoleRequest, Roles
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User as AuthUser
from django.contrib.auth.models import Group
from django.contrib import messages
from django.db import transaction

@admin.register(User)
class StaffUserAdmin(UserAdmin):
    list_display = (
        "username",
        "staff_id",
        "first_name",
        "last_name",
        "department",
        "is_active",
    )
    list_filter = ("department", "is_active", "groups")
    search_fields = (
        "username",
        "staff_id",
        "first_name",
        "last_name",
        "email",
    )

    fieldsets = UserAdmin.fieldsets + (
        (
            "Organisation",
            {
                "fields": (
                    "staff_id",
                    "department",
                    "job_title",
                    "phone",
                )
            },
        ),
        (
            "Account state",
            {
                "fields": (
                    "must_change_password",
                    "email_verified",
                    "signup_pending",
                    "email_notifications",
                    "failed_login_count",
                    "locked_until",
                )
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Organisation",
            {
                "fields": (
                    "staff_id",
                    "department",
                    "job_title",
                )
            },
        ),
    )


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "unit", "head")
    list_filter = ("unit",)
    search_fields = (
        "name",
        "head__first_name",
        "head__last_name",
        "head__staff_id",
    )
    autocomplete_fields = ("head",)
    list_editable = ("unit", "head")
    ordering = ("unit", "name")




@admin.register(RoleRequest)
class RoleRequestAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "requested_role",
        "department",
        "status",
        "created_at",
        "reviewed_by",
    )
    list_filter = ("requested_role", "status", "department")
    search_fields = (
        "user__username",
        "user__staff_id",
        "user__first_name",
        "user__last_name",
    )
    readonly_fields = (
        "created_at",
        "reviewed_by",
        "reviewed_at",
        "status",
    )
    ordering = ("-created_at",)

    actions = ("approve_requests", "reject_requests")

    @admin.action(description="Approve selected role requests")
    def approve_requests(self, request, queryset):
        approved = 0
        skipped = 0

        for role_request in queryset.filter(
            status=RoleRequest.Status.PENDING
        ):
            if (
                role_request.requested_role == RoleRequest.RequestedRole.HOD
                and not role_request.department
            ):
                skipped += 1
                continue

            with transaction.atomic():
                if role_request.requested_role == RoleRequest.RequestedRole.HOD:
                    role_request.department.head = role_request.user
                    role_request.department.save(update_fields=["head"])

                elif role_request.requested_role == RoleRequest.RequestedRole.HR_MANAGER:
                    group, _ = Group.objects.get_or_create(
                        name=Roles.HR_MANAGER
                    )
                    role_request.user.groups.add(group)

                role_request.status = RoleRequest.Status.APPROVED
                role_request.reviewed_by = request.user
                role_request.reviewed_at = timezone.now()
                role_request.save(
                    update_fields=[
                        "status",
                        "reviewed_by",
                        "reviewed_at",
                    ]
                )

            approved += 1

        self.message_user(
            request,
            f"{approved} request(s) approved. {skipped} skipped because an HOD request had no department.",
            level=messages.SUCCESS if approved else messages.WARNING,
        )

    @admin.action(description="Reject selected role requests")
    def reject_requests(self, request, queryset):
        rejected = 0

        for role_request in queryset.filter(
            status=RoleRequest.Status.PENDING
        ):
            role_request.status = RoleRequest.Status.REJECTED
            role_request.reviewed_by = request.user
            role_request.reviewed_at = timezone.now()
            role_request.save(
                update_fields=[
                    "status",
                    "reviewed_by",
                    "reviewed_at",
                ]
            )
            rejected += 1

        self.message_user(
            request,
            f"{rejected} request(s) rejected.",
            level=messages.SUCCESS,
        )


@admin.register(OAuthIdentity)
class OAuthIdentityAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "email", "created_at")
    search_fields = ("user__username", "email")
