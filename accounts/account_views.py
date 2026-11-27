import json

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import codes, emails
from .auth_views import check_password_strength, code_error
from .models import User
from .serializers import (
    EmailChangeConfirmSerializer, EmailChangeRequestSerializer, MeSerializer, ProfileSerializer, SetPasswordSerializer,
)
from .session import new_token
from .signup import domain_allowed, domain_hint

Purpose = codes.Purpose


class ProfileView(APIView):
    def get(self, request):
        return Response(MeSerializer(request.user).data)

    def patch(self, request):
        ser = ProfileSerializer(request.user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(MeSerializer(request.user).data)


class EmailChangeRequestView(APIView):
    throttle_scope = "code"

    def post(self, request):
        ser = EmailChangeRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user, new = request.user, codes.norm(ser.validated_data["new_email"])
        if user.has_usable_password() and not user.check_password(ser.validated_data.get("password", "")):
            raise ValidationError({"password": "Enter your current password to change your email."})
        if new == (user.email or "").lower():
            raise ValidationError({"new_email": "That is already your email address."})
        if not domain_allowed(new):
            raise ValidationError({"new_email": f"Please use your institution email address ({domain_hint()})."})
        if User.objects.filter(email__iexact=new).exclude(pk=user.pk).exists():
            raise ValidationError({"new_email": "Another account already uses this email address."})
        try:
            row, code = codes.issue_code(purpose=Purpose.EMAIL_CHANGE, email=new, user=user)
        except codes.CodeError as exc:
            return code_error(exc)
        if not emails.send_code(new, code, "email_change", user.first_name):
            codes.consume(row)
            return Response({"detail": "We could not send the email just now. Please try again in a few minutes."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"detail": f"We sent a code to {new}.", "resend_in": settings.CODE_RESEND_SECONDS})


class EmailChangeConfirmView(APIView):
    throttle_scope = "code"

    def post(self, request):
        ser = EmailChangeConfirmSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        new = codes.norm(ser.validated_data["new_email"])
        try:
            row = codes.check_code(purpose=Purpose.EMAIL_CHANGE, email=new, code=ser.validated_data["code"])
        except codes.CodeError as exc:
            return code_error(exc)
        if row.user_id != request.user.pk or User.objects.filter(email__iexact=new).exclude(pk=request.user.pk).exists():
            return code_error(codes.CodeError("That code is not valid or has expired. Request a new one."))
        old = request.user.email
        request.user.email, request.user.email_verified = new, True
        request.user.save(update_fields=["email", "email_verified"])
        codes.consume(row)
        if old:
            emails.send_notice(old, "Your Vecta email address was changed", f"The email address on your Vecta account was changed to {new}.")
        return Response(MeSerializer(request.user).data)


class SetPasswordView(APIView):
    """For accounts created through Google/Microsoft that have no password yet."""

    def post(self, request):
        if request.user.has_usable_password():
            raise ValidationError({"detail": "You already have a password. Use 'change password' instead."})
        ser = SetPasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        check_password_strength(ser.validated_data["new_password"], request.user)
        request.user.set_password(ser.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response({"token": new_token(request.user).key, "user": MeSerializer(request.user).data})


class RevokeSessionsView(APIView):
    """Sign out every other device; this one stays signed in with a fresh token."""

    def post(self, request):
        return Response({"token": new_token(request.user).key})


class IdentitiesView(APIView):
    def get(self, request):
        from .oauth import PROVIDERS

        return Response([{"provider": i.provider, "name": PROVIDERS.get(i.provider, {}).get("name", i.provider), "email": i.email, "linked_at": i.created_at}
                         for i in request.user.identities.all()])


class IdentityDetailView(APIView):
    def delete(self, request, provider):
        ident = request.user.identities.filter(provider=provider).first()
        if not ident:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not request.user.has_usable_password() and request.user.identities.count() <= 1:
            raise ValidationError({"detail": "Set a password first. Otherwise you would have no way to sign in."})
        ident.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExportView(APIView):
    """Everything Vecta holds about me, as a JSON download."""

    def get(self, request):
        from leave.models import LeaveBalance, LeaveRequest, Notification
        from leave.serializers import LeaveBalanceSerializer, LeaveRequestDetailSerializer, NotificationSerializer

        u = request.user
        reqs = LeaveRequest.objects.filter(user=u).select_related("user", "leave_type", "current_approver", "relief_officer").prefetch_related("actions__actor")
        data = {
            "exported_at": timezone.now(), "profile": MeSerializer(u).data,
            "leave_balances": LeaveBalanceSerializer(LeaveBalance.objects.filter(user=u).select_related("leave_type"), many=True).data,
            "leave_requests": LeaveRequestDetailSerializer(reqs, many=True, context={"request": request}).data,
            "notifications": NotificationSerializer(Notification.objects.filter(user=u), many=True).data,
        }
        resp = HttpResponse(json.dumps(data, indent=2, default=str), content_type="application/json")
        resp["Content-Disposition"] = 'attachment; filename="vecta-my-data.json"'
        return resp
