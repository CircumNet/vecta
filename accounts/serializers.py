from django.contrib.auth.password_validation import validate_password
from django.utils.crypto import get_random_string
from rest_framework import serializers

from .models import Department, Roles, User, HRInvitation


class DepartmentSerializer(serializers.ModelSerializer):
    head_name = serializers.CharField(source="head.display_name", read_only=True, default=None)

    class Meta:
        model = Department
        fields = ["id", "name", "head", "head_name"]



class UserSerializer(serializers.ModelSerializer):
    roles = serializers.ListField(child=serializers.CharField(), read_only=True)
    department_name = serializers.CharField(
        source="department.name",
        read_only=True,
        default=None,
    )
    full_name = serializers.CharField(source="display_name", read_only=True)
    needs_setup = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "staff_id", "first_name", "last_name",
            "full_name", "email", "department", "department_name",
            "job_title", "roles", "is_active", "must_change_password",
            "needs_setup",
        ]
        read_only_fields = fields

    def get_needs_setup(self, obj):
        """A new self-registered person HR has not placed in the organisation yet."""
        if not obj.is_active or obj.department_id or obj.is_superuser:
            return False
        return not obj.groups.filter(
            name__in=[Roles.HR_MANAGER, Roles.ADMIN]
        ).exists()



class MeSerializer(UserSerializer):
    is_delegate = serializers.SerializerMethodField()
    has_password = serializers.SerializerMethodField()
    linked_providers = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + [
            "is_delegate", "phone", "email_notifications", "email_verified", "has_password", "linked_providers", "last_login",
        ]
        read_only_fields = fields

    def get_is_delegate(self, obj):
        from leave.services import active_delegators

        return bool(active_delegators(obj))

    def get_has_password(self, obj):
        return obj.has_usable_password()

    def get_linked_providers(self, obj):
        return sorted(obj.identities.values_list("provider", flat=True))


class UserWriteSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = [
            "username", "email", "first_name", "last_name", "staff_id",
            "department", "job_title", "is_active", "password",
        ]

    def validate_email(self, value):
        qs = User.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if value and qs.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        generated = not password
        password = password or get_random_string(12)
        user = User(**validated_data)
        user.set_password(password)
        user.must_change_password = True
        user.save()
        user.temporary_password = password if generated else None
        return user

    def update(self, instance, validated_data):
        validated_data.pop("password", None)  # passwords change only via the auth endpoints
        return super().update(instance, validated_data)


class RolesSerializer(serializers.Serializer):
    roles = serializers.ListField(child=serializers.ChoiceField(choices=Roles.ASSIGNABLE), allow_empty=True)


# ---------------------------------------------------------------- auth
class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=False, allow_blank=True)
    username = serializers.CharField(required=False, allow_blank=True)  # accepted for older clients
    password = serializers.CharField()



class RegisterSerializer(serializers.Serializer):
    staff_id = serializers.CharField(max_length=30)
    first_name = serializers.CharField(max_length=60)
    last_name = serializers.CharField(max_length=60)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30)
    department = serializers.CharField(max_length=150)
    role = serializers.ChoiceField(choices=[
        ("staff", "Staff"),
        ("department_head", "Head of Department"),
    ])
    password = serializers.CharField()

    def validate_department(self, value):
        from .models import Department

        try:
            unit_label, department_name = value.split(":", 1)
        except ValueError:
            raise serializers.ValidationError(
                "Please select a valid department."
            )

        unit_map = {
            "Academic": "academic",
            "Non-academic": "non_academic",
        }

        unit = unit_map.get(unit_label.strip())

        if not unit:
            raise serializers.ValidationError(
                "Please select a valid department unit."
            )

        try:
            return Department.objects.get(
                unit=unit,
                name=department_name.strip()
            )
        except Department.DoesNotExist:
            raise serializers.ValidationError(
                "The selected department does not exist."
            )



class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class EmailCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=12)


class ResetSerializer(serializers.Serializer):
    reset_token = serializers.CharField()
    new_password = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField()


class SetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField()


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "email_notifications"]
        extra_kwargs = {"first_name": {"required": False, "allow_blank": False}, "last_name": {"required": False, "allow_blank": False}}


class EmailChangeRequestSerializer(serializers.Serializer):
    new_email = serializers.EmailField()
    password = serializers.CharField(required=False, allow_blank=True)


class EmailChangeConfirmSerializer(serializers.Serializer):
    new_email = serializers.EmailField()
    code = serializers.CharField(max_length=12)


class HRInviteSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value, groups__name=Roles.HR_MANAGER).exists():
            raise serializers.ValidationError("An active HR Manager with this email already exists.")
        if HRInvitation.objects.filter(email__iexact=value, used_at__isnull=True, expires_at__gt=timezone.now()).exists():
            raise serializers.ValidationError("A valid invitation already exists for this email.")
        return value.lower()

class HRRegisterSerializer(serializers.Serializer):
    invitation_token = serializers.CharField()
    first_name = serializers.CharField(max_length=60)
    last_name = serializers.CharField(max_length=60)
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, attrs):
        inv = HRInvitation.objects.filter(token=attrs["invitation_token"], used_at__isnull=True, expires_at__gt=timezone.now()).first()
        if not inv:
            raise serializers.ValidationError({"invitation_token": "This invitation token is invalid or has expired."})
        if inv.email.lower() != attrs["email"].lower():
            raise serializers.ValidationError({"email": "The email does not match the one on the invitation."})
        if User.objects.filter(email__iexact=attrs["email"]).exists():
            raise serializers.ValidationError({"email": "An account with this email already exists."})
        attrs["invitation"] = inv
        return attrs