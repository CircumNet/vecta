"""One-time email codes: issue, verify, and exchange for a short-lived reset token."""
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import EmailCode

Purpose = EmailCode.Purpose


class CodeError(Exception):
    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.message, self.retry_after = message, retry_after


def _h(value):
    return salted_hmac("vecta.emailcode", value).hexdigest()


def norm(email):
    return (email or "").strip().lower()


def issue_code(*, purpose, email, user=None, cooldown=True):
    """Create a fresh code (invalidating older ones). Returns (row, plaintext_code)."""
    email, now = norm(email), timezone.now()
    open_codes = EmailCode.objects.filter(purpose=purpose, email=email, consumed_at__isnull=True)
    last = open_codes.order_by("-created_at").first()
    if cooldown and last:
        waited = (now - last.created_at).total_seconds()
        if waited < settings.CODE_RESEND_SECONDS:
            raise CodeError("Please wait a moment before requesting another code.", retry_after=int(settings.CODE_RESEND_SECONDS - waited) + 1)
    open_codes.update(consumed_at=now)
    code = f"{secrets.randbelow(1_000_000):06d}"
    row = EmailCode.objects.create(
        purpose=purpose, email=email, user=user, code_hash=_h(f"{purpose}:{email}:{code}"),
        expires_at=now + timedelta(minutes=settings.CODE_TTL_MINUTES),
    )
    return row, code


def check_code(*, purpose, email, code):
    """
    Validate a code. Counts every attempt; after CODE_MAX_ATTEMPTS the code is dead.
    The counter is committed *before* any error is raised (raising inside the transaction would roll it back).
    """
    email, now = norm(email), timezone.now()
    problem = None
    with transaction.atomic():
        row = (
            EmailCode.objects.select_for_update()
            .filter(purpose=purpose, email=email, consumed_at__isnull=True, verified_at__isnull=True, expires_at__gt=now)
            .order_by("-created_at").first()
        )
        if not row or row.attempts >= settings.CODE_MAX_ATTEMPTS:
            problem = "That code is not valid or has expired. Request a new one."
        else:
            row.attempts += 1
            row.save(update_fields=["attempts"])
            if not constant_time_compare(row.code_hash, _h(f"{purpose}:{email}:{(code or '').strip()}")):
                left = settings.CODE_MAX_ATTEMPTS - row.attempts
                problem = "That code is incorrect." + (f" {left} attempt{'s' if left != 1 else ''} left." if left else " Request a new code.")
    if problem:
        raise CodeError(problem)
    return row


def consume(row):
    row.consumed_at = timezone.now()
    row.save(update_fields=["consumed_at"])


def mint_token(row):
    """After a correct reset code: hand back a one-time token for the final 'choose password' step."""
    token = secrets.token_urlsafe(32)
    row.token_hash, row.verified_at = _h("tok:" + token), timezone.now()
    row.expires_at = row.verified_at + timedelta(minutes=settings.CODE_TTL_MINUTES)
    row.save(update_fields=["token_hash", "verified_at", "expires_at"])
    return token


def redeem_token(token, purpose):
    row = EmailCode.objects.filter(
        token_hash=_h("tok:" + (token or "")), purpose=purpose, verified_at__isnull=False,
        consumed_at__isnull=True, expires_at__gt=timezone.now(),
    ).select_related("user").first()
    if not row:
        raise CodeError("This reset session has expired. Please start again.")
    return row
