from django.contrib.auth.models import Group
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import emails
from .auth_views import check_password_strength
from .models import Department, Roles, User
from .permissions import IsAdminRole, IsHR, ReadAnyWriteHR
from .serializers import (
    ChangePasswordSerializer, DepartmentSerializer, MeSerializer, RolesSerializer, UserSerializer, UserWriteSerializer,
)
from .session import new_token


class LogoutView(APIView):
    allow_password_change_pending = True

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    allow_password_change_pending = True

    def get(self, request):
        return Response(MeSerializer(request.user).data)


class ChangePasswordView(APIView):
    allow_password_change_pending = True

    def post(self, request):
        ser = ChangePasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = request.user
        if not user.has_usable_password():
            raise ValidationError({"detail": "Your account has no password yet. Use 'set a password' instead."})
        if not user.check_password(ser.validated_data["old_password"]):
            raise ValidationError({"old_password": "Incorrect password."})
        check_password_strength(ser.validated_data["new_password"], user)
        user.set_password(ser.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        if user.email:
            emails.send_notice(user.email, "Your Vecta password was changed", "Your password was just changed from your account page.")
        return Response({"token": new_token(user).key})


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.select_related("head")
    serializer_class = DepartmentSerializer
    permission_classes = [ReadAnyWriteHR]
    pagination_class = None


class UserViewSet(viewsets.ModelViewSet):
    """HR/admin manage accounts. New accounts start as plain staff."""

    queryset = User.objects.filter(signup_pending=False).select_related("department").order_by("last_name", "first_name", "username")
    permission_classes = [IsHR]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return UserWriteSerializer
        return UserSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("department"):
            qs = qs.filter(department_id=p["department"])
        if p.get("needs_setup") in ("1", "true"):
            qs = qs.filter(is_active=True, is_superuser=False, department__isnull=True).exclude(groups__name__in=[Roles.HR_MANAGER, Roles.ADMIN])
        if p.get("search"):
            s = p["search"]
            qs = qs.filter(
                Q(username__icontains=s) | Q(first_name__icontains=s) | Q(last_name__icontains=s) | Q(staff_id__icontains=s) | Q(email__icontains=s)
            )
        return qs

    def create(self, request, *args, **kwargs):
        ser = UserWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        data = UserSerializer(user).data
        if getattr(user, "temporary_password", None):
            data["temporary_password"] = user.temporary_password
        return Response(data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        ser = UserWriteSerializer(self.get_object(), data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        if not user.is_active:
            Token.objects.filter(user=user).delete()
        return Response(UserSerializer(user).data)

    def perform_destroy(self, instance):
        # Never hard-delete: leave history must survive. Deactivate instead.
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        Token.objects.filter(user=instance).delete()

    @action(detail=True, methods=["post"], url_path="roles", permission_classes=[IsAdminRole])
    def set_roles(self, request, pk=None):
        user = self.get_object()
        ser = RolesSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        wanted = set(ser.validated_data["roles"]) | {Roles.STAFF}
        user.groups.set(Group.objects.filter(name__in=wanted))
        return Response(UserSerializer(user).data)

    @action(detail=True, methods=["get"], url_path="balances")
    def balances(self, request, pk=None):
        from leave.serializers import LeaveBalanceSerializer
        from leave.services import ensure_balances

        user = self.get_object()
        year = int(request.query_params.get("year") or 0) or None
        return Response(LeaveBalanceSerializer(ensure_balances(user, year), many=True).data)
