from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import codes, emails, oauth
from .models import User, Roles, RoleRequest, HRInvitation
from .serializers import (
    EmailCodeSerializer, EmailSerializer, LoginSerializer, RegisterSerializer, ResetSerializer, HRInviteSerializer, HRRegisterSerializer,
)
from .session import session_payload
from .signup import alert_hr_new_account, domain_allowed, domain_hint, unique_username
from .permissions import IsHR

from django.contrib.auth.models import Group
from django.db import transaction


Purpose = codes.Purpose
def mail_down():
    return Response({"detail": "We could not send the verification email just now. Please try again in a few minutes, or ask your administrator to check the email settings."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


def check_password_strength(password, user=None):
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise ValidationError({"new_password" if user else "password": list(exc.messages)})


def code_error(exc):
    body = {"detail": exc.message}
    if exc.retry_after:
        body["retry_after"] = exc.retry_after
    return Response(body, status=status.HTTP_429_TOO_MANY_REQUESTS if exc.retry_after else status.HTTP_400_BAD_REQUEST)


class Public(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []


class ConfigView(Public):
    """What the sign-in screen needs to know before it draws itself."""

    def get(self, request):
        return Response({
            "providers": oauth.enabled(),
            "registration_enabled": settings.ALLOW_SELF_REGISTRATION,
            "allowed_domains": settings.ALLOWED_EMAIL_DOMAINS,
            "code_minutes": settings.CODE_TTL_MINUTES,
            "resend_seconds": settings.CODE_RESEND_SECONDS,
        })


# ---------------------------------------------------------------- login
class LoginView(Public):
    throttle_scope = "login"

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ident = (ser.validated_data.get("identifier") or ser.validated_data.get("username") or "").strip()
        password = ser.validated_data["password"]
        
        # NEW: Get the role requirement from the frontend
        role_required = request.data.get("role_required")

        lookup = {"email__iexact": ident} if "@" in ident else {"username__iexact": ident}
        user = User.objects.filter(**lookup).first() if ident else None
        invalid = Response({"detail": "Incorrect email/username or password."}, status=status.HTTP_401_UNAUTHORIZED)

        if user is None:
            make_password(password)  # keep timing similar whether or not the account exists
            return invalid

        # NEW: Enforce the role requirement
        if role_required == "hr_manager" and not user.is_hr:
            return Response({"detail": "This account is not authorised for HR Manager access."}, status=status.HTTP_403_FORBIDDEN)

        now = timezone.now()
        if user.locked_until and user.locked_until > now:
            mins = int((user.locked_until - now).total_seconds() // 60) + 1
            return Response({"detail": f"Too many failed attempts. Try again in {mins} minute{'s' if mins != 1 else ''}, or reset your password."},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)
        if user.signup_pending and user.check_password(password):
            return Response({"detail": "Please verify your email address to finish creating your account.", "code": "verify_email", "email": user.email},
                            status=status.HTTP_403_FORBIDDEN)
        authed = authenticate(request, username=user.username, password=password)
        if not authed or not authed.is_active:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.LOGIN_MAX_ATTEMPTS:
                user.failed_login_count, user.locked_until = 0, now + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
            user.save(update_fields=["failed_login_count", "locked_until"])
            return invalid
        if user.failed_login_count or user.locked_until:
            user.failed_login_count, user.locked_until = 0, None
            user.save(update_fields=["failed_login_count", "locked_until"])
        return Response(session_payload(user))

# ---------------------------------------------------------------- registration

class RegisterView(Public):
    throttle_scope = "register"

    def post(self, request):
        if not settings.ALLOW_SELF_REGISTRATION:
            return Response(
                {"detail": "Self-registration is turned off. Ask HR to create your account."},
                status=status.HTTP_403_FORBIDDEN
            )

        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        email = codes.norm(d["email"])

        if not domain_allowed(email):
            raise ValidationError({
                "email": f"Please use your institution email address ({domain_hint()})."
            })

        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError({
                "email": "An account with this email address already exists."
            })

        if User.objects.filter(staff_id__iexact=d["staff_id"]).exists():
            raise ValidationError({
                "staff_id": "This Staff ID is already registered."
            })

        check_password_strength(d["password"], None)

        department = d["department"]
        requested_role = d["role"]

        with transaction.atomic():
            user = User.objects.create(
                username=unique_username(email),
                email=email,
                staff_id=d["staff_id"].strip(),
                first_name=d["first_name"].strip(),
                last_name=d["last_name"].strip(),
                phone=d["phone"].strip(),
                department=department,
                is_active=True,
                signup_pending=False,
                email_verified=True,
                must_change_password=False,
            )

            user.set_password(d["password"])
            user.save()

            staff_group, _ = Group.objects.get_or_create(name=Roles.STAFF)
            user.groups.add(staff_group)

            if requested_role in (
                Roles.DEPARTMENT_HEAD,
                Roles.HR_MANAGER,
            ):
                RoleRequest.objects.create(
                    user=user,
                    requested_role=requested_role,
                    department=(
                        department
                        if requested_role == Roles.DEPARTMENT_HEAD
                        else None
                    ),
                )
        alert_hr_new_account(user)

        return Response(
            {
                "detail": "Account created successfully. You can now sign in."
            },
            status=status.HTTP_201_CREATED
        )



class RegisterVerifyView(Public):
    throttle_scope = "code"

    def post(self, request):
        ser = EmailCodeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            row = codes.check_code(purpose=Purpose.REGISTER, email=ser.validated_data["email"], code=ser.validated_data["code"])
        except codes.CodeError as exc:
            return code_error(exc)
        user = row.user
        if not user or not user.signup_pending:
            return code_error(codes.CodeError("That code is not valid or has expired. Request a new one."))
        user.is_active, user.signup_pending, user.email_verified = True, False, True
        user.save(update_fields=["is_active", "signup_pending", "email_verified"])
        codes.consume(row)
        alert_hr_new_account(user)
        return Response(session_payload(user))


class RegisterResendView(Public):
    throttle_scope = "code"

    def post(self, request):
        ser = EmailSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = codes.norm(ser.validated_data["email"])
        user = User.objects.filter(email__iexact=email, signup_pending=True).first()
        if user:
            try:
                row, code = codes.issue_code(purpose=Purpose.REGISTER, email=email, user=user)
                if not emails.send_code(email, code, "register", user.first_name):
                    codes.consume(row)
                    return mail_down()
            except codes.CodeError as exc:
                return code_error(exc)
        return Response({"detail": "If that sign-up is waiting, we have sent a new code.", "resend_in": settings.CODE_RESEND_SECONDS})


class ForgotView(Public):
    throttle_scope = "code"

    def post(self, request):
        ser = EmailSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = codes.norm(ser.validated_data["email"])
        user = User.objects.filter(email__iexact=email, is_active=True, signup_pending=False).first()
        if user:
            try:
                row, code = codes.issue_code(purpose=Purpose.RESET, email=user.email, user=user)
                if not emails.send_code(user.email, code, "reset", user.first_name):
                    codes.consume(row)
                    return mail_down()
            except codes.CodeError:
                pass
        # Identical response whether or not the address is registered.
        return Response({"detail": "If that email is registered, we have sent a 6-digit code.", "resend_in": settings.CODE_RESEND_SECONDS})


class VerifyResetCodeView(Public):
    throttle_scope = "code"

    def post(self, request):
        ser = EmailCodeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            row = codes.check_code(purpose=Purpose.RESET, email=ser.validated_data["email"], code=ser.validated_data["code"])
        except codes.CodeError as exc:
            return code_error(exc)
        return Response({"reset_token": codes.mint_token(row)})


class ResetPasswordView(Public):
    throttle_scope = "code"

    def post(self, request):
        ser = ResetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            row = codes.redeem_token(ser.validated_data["reset_token"], Purpose.RESET)
        except codes.CodeError as exc:
            return code_error(exc)
        user = row.user
        check_password_strength(ser.validated_data["new_password"], user)
        user.set_password(ser.validated_data["new_password"])
        user.must_change_password, user.failed_login_count, user.locked_until = False, 0, None
        user.save(update_fields=["password", "must_change_password", "failed_login_count", "locked_until"])
        codes.consume(row)
        Token.objects.filter(user=user).delete()  # sign out everywhere
        emails.send_notice(user.email, "Your Vecta password was changed", "Your password was just reset using an emailed code, and every device was signed out.")
        return Response({"detail": "Password updated. You can now sign in."})

#---- HR Views


class HRInviteView(APIView):
    """Only existing HR managers can generate invitation tokens."""
    permission_classes = [IsHR]

    def post(self, request):
        ser = HRInviteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        inv = HRInvitation.objects.create(email=ser.validated_data["email"], created_by=request.user)
        # In production, send this via email instead of returning it directly
        return Response({"token": inv.token, "expires_at": inv.expires_at, "detail": "Invitation token generated."}, status=201)


class HRRegisterView(Public):
    throttle_scope = "register"

    def post(self, request):
        ser = HRRegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        inv = d["invitation"]

        with transaction.atomic():
            user = User.objects.create(
                username=unique_username(d["email"]),
                email=d["email"].lower(),
                first_name=d["first_name"],
                last_name=d["last_name"],
                is_active=True,
                email_verified=True,
                must_change_password=False,
            )
            user.set_password(d["password"])
            user.save()
            
            # Assign HR Manager role
            hr_group, _ = Group.objects.get_or_create(name=Roles.HR_MANAGER)
            user.groups.add(hr_group)

            # Mark invitation as used
            inv.used_at = timezone.now()
            inv.save(update_fields=["used_at"])

        return Response({"detail": "HR Manager account created successfully."}, status=201)