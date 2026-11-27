from rest_framework.permissions import BasePermission


class IsActiveAndPasswordSet(BasePermission):
    """Default permission: logged in, active, and not stuck on a forced password change."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        if user.must_change_password and not getattr(view, "allow_password_change_pending", False):
            self.message = "You must change your password before continuing."
            return False
        return True


class IsHR(IsActiveAndPasswordSet):
    message = "HR access required."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_hr


class IsAdminRole(IsActiveAndPasswordSet):
    message = "Admin access required."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_admin


class ReadAnyWriteHR(IsActiveAndPasswordSet):
    """Any signed-in user may read; only HR/admin may change."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.method in ("GET", "HEAD", "OPTIONS") or request.user.is_hr
