from accounts.permissions import IsActiveAndPasswordSet

from . import services


class CanViewLeaveRequest(IsActiveAndPasswordSet):
    """Object-level: owner, assigned approver, the owner's department head, HR."""

    def has_object_permission(self, request, view, obj):
        return services.can_view(obj, request.user)
