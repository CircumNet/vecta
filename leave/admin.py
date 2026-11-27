from django.contrib import admin

from .models import BlackoutPeriod, Delegation, Holiday, LeaveAction, LeaveBalance, LeaveRequest, LeaveType, Notification


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "default_days", "requires_document", "is_paid", "carry_over_cap", "is_active")


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ("user", "leave_type", "year", "entitled", "used", "pending")
    list_filter = ("year", "leave_type")
    search_fields = ("user__username", "user__first_name", "user__last_name")


class LeaveActionInline(admin.TabularInline):
    model = LeaveAction
    extra = 0
    can_delete = False
    readonly_fields = ("actor", "action", "comment", "created_at")

    def has_add_permission(self, request, obj=None):
        return False



@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = (
        "user","leave_type","start_date","end_date","working_days","status","current_approver",
    )
    list_filter = ("status", "leave_type")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "user__staff_id",
    )
    inlines = [LeaveActionInline]
    actions = ["delete_selected"]
    ordering = ("-start_date",)

admin.site.register(Holiday)
admin.site.register(Notification)


@admin.register(BlackoutPeriod)
class BlackoutAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "department")


@admin.register(Delegation)
class DelegationAdmin(admin.ModelAdmin):
    list_display = ("delegator", "delegate", "start_date", "end_date", "is_active")
