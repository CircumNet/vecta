import urllib.parse

from django.conf import settings
from django.http import HttpResponseRedirect
from rest_framework.exceptions import NotAuthenticated, NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import oauth
from .auth_views import Public
from .session import session_payload


class OAuthStartView(APIView):
    """POST {mode: login|link}. Returns the provider URL to send the browser to."""

    permission_classes = [AllowAny]

    def post(self, request, provider):
        if not oauth.conf(provider):
            raise NotFound("That sign-in method is not available.")
        mode = request.data.get("mode", "login")
        if mode not in ("login", "link"):
            raise ValidationError({"mode": "Use 'login' or 'link'."})
        user = None
        if mode == "link":
            if not request.user.is_authenticated:
                raise NotAuthenticated()
            user = request.user
        return Response({"url": oauth.start_flow(provider, mode, user)})


def _back(**params):
    return HttpResponseRedirect(f"{settings.SITE_URL.rstrip('/')}/?{urllib.parse.urlencode(params)}")


class OAuthCallbackView(Public):
    """The provider redirects the browser here. We always send it back to the app, never show raw errors."""

    def get(self, request, provider):
        if request.GET.get("error"):
            return _back(oauth_error="Sign-in was cancelled." if request.GET["error"] == "access_denied" else "The provider could not sign you in.")
        try:
            flow, profile = oauth.finish_flow(provider, request.GET.get("state"), request.GET.get("code"))
            if flow.mode == "link":
                oauth.link_identity(flow.user, provider, profile)
                return _back(oauth_linked=provider)
            user = oauth.login_or_register(provider, profile)
            return _back(oauth_code=oauth.make_exchange_code(flow, user))
        except oauth.OAuthError as exc:
            return _back(oauth_error=str(exc))


class OAuthExchangeView(Public):
    throttle_scope = "code"

    def post(self, request):
        try:
            user = oauth.redeem_exchange_code(request.data.get("code"))
        except oauth.OAuthError as exc:
            raise ValidationError({"detail": str(exc)})
        if not user.is_active:
            raise ValidationError({"detail": "This account is deactivated. Please contact HR."})
        return Response(session_payload(user))
