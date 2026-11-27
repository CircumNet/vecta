"""Token authentication with a finite lifetime for browser/API sessions."""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ExpiringTokenAuthentication(TokenAuthentication):
    """Reject and remove tokens older than TOKEN_TTL_DAYS."""

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        ttl_days = max(1, int(getattr(settings, "TOKEN_TTL_DAYS", 30)))
        if token.created <= timezone.now() - timedelta(days=ttl_days):
            token.delete()
            raise AuthenticationFailed("Your session has expired. Please sign in again.")
        return user, token
