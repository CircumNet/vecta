import re

from django.conf import settings
from django.db.models import Q

from .models import Roles, User


def domain_allowed(email):
    domains = settings.ALLOWED_EMAIL_DOMAINS
    return not domains or email.rsplit("@", 1)[-1].lower() in domains


def domain_hint():
    return ", ".join("@" + d for d in settings.ALLOWED_EMAIL_DOMAINS)


def unique_username(email):
    base = re.sub(r"[^a-z0-9._-]", "", email.split("@")[0].lower())[:30] or "user"
    name, i = base, 1
    while User.objects.filter(username__iexact=name).exists():
        i += 1
        name = f"{base}{i}"
    return name


def split_name(full):
    parts = (full or "").split()
    return (parts[0] if parts else ""), (" ".join(parts[1:]) if len(parts) > 1 else "")

def alert_hr_new_account(user):
    """Tell HR when a person creates an account."""
    from leave.services import notify
    from django.db.models import Q

    hr = User.objects.filter(is_active=True).filter(
        Q(groups__name__in=[Roles.HR_MANAGER, Roles.ADMIN]) | Q(is_superuser=True)
    ).distinct()
    
    dept = user.department.name if user.department else "No Department"
    staff_id = user.staff_id or "N/A"
    
    message = (
        f"New account created: {user.display_name} ({user.email}). "
        f"Staff ID: {staff_id}. Department: {dept}. "
        f"Please review their account details."
    )
    
    for h in hr:
        notify(h, "signup", message)