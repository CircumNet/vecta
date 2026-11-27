"""
OAuth 2.0 authorization-code flow with PKCE for Google and Microsoft (OpenID Connect).
Only the sign-in identity is requested (openid email profile); no mailbox access.
"""
import base64
import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .codes import _h
from .models import OAuthFlow, OAuthIdentity, User
from .signup import alert_hr_new_account, domain_allowed, domain_hint, split_name, unique_username


class OAuthError(Exception):
    pass


PROVIDERS = {
    "google": {
        "name": "Google",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
        "extra": {"prompt": "select_account"},
    },
    "microsoft": {
        "name": "Microsoft",
        "auth_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/oidc/userinfo",
        "scope": "openid email profile",
        "extra": {"prompt": "select_account"},
    },
}


def conf(name):
    base = PROVIDERS.get(name)
    if not base:
        return None
    key = name.upper()
    cid, secret = getattr(settings, f"{key}_CLIENT_ID", ""), getattr(settings, f"{key}_CLIENT_SECRET", "")
    if not (cid and secret):
        return None
    tenant = getattr(settings, "MICROSOFT_TENANT", "organizations")
    c = {k: (v.format(tenant=tenant) if isinstance(v, str) else v) for k, v in base.items()}
    # Google states email_verified explicitly. Microsoft does not, and its `email` claim can be unverified in
    # multi-tenant setups, so we only trust it when the app is pinned to one specific tenant.
    c.update(client_id=cid, client_secret=secret, trust_email=(name == "microsoft" and tenant not in ("common", "organizations", "consumers")))
    return c


def enabled():
    return [{"id": k, "name": v["name"]} for k, v in PROVIDERS.items() if conf(k)]


def redirect_uri(provider):
    return f"{settings.SITE_URL.rstrip('/')}/api/auth/oauth/{provider}/callback/"


# ---- network (small and patchable) ----------------------------------------
def _open(req):
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError:
        raise OAuthError("The sign-in provider rejected the request. Please try again.")
    except Exception:
        raise OAuthError("Could not reach the sign-in provider. Please try again.")


def http_post_form(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    return _open(req)


def http_get_json(url, headers):
    return _open(urllib.request.Request(url, headers={**headers, "Accept": "application/json"}))


# ---- flow ------------------------------------------------------------------
def start_flow(provider, mode, user=None):
    c = conf(provider)
    now = timezone.now()
    OAuthFlow.objects.filter(expires_at__lt=now - timedelta(hours=1)).delete()
    verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    OAuthFlow.objects.create(state=state, provider=provider, mode=mode, user=user, code_verifier=verifier, expires_at=now + timedelta(minutes=10))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = {
        "client_id": c["client_id"], "redirect_uri": redirect_uri(provider), "response_type": "code", "scope": c["scope"],
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256", **c["extra"],
    }
    return c["auth_url"] + "?" + urllib.parse.urlencode(params)


def finish_flow(provider, state, code):
    """Validate state, trade the code for the user's identity. Returns (flow, profile)."""
    c = conf(provider)
    flow = OAuthFlow.objects.filter(state=state or "-", provider=provider, used_at__isnull=True, expires_at__gt=timezone.now()).first()
    if not c or not flow or not code:
        raise OAuthError("This sign-in attempt has expired. Please try again.")
    flow.used_at = timezone.now()
    flow.save(update_fields=["used_at"])
    tokens = http_post_form(c["token_url"], {
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(provider),
        "client_id": c["client_id"], "client_secret": c["client_secret"], "code_verifier": flow.code_verifier,
    })
    if not tokens.get("access_token"):
        raise OAuthError("The sign-in provider did not return a token.")
    info = http_get_json(c["userinfo_url"], {"Authorization": "Bearer " + tokens["access_token"]})
    verified = info.get("email_verified") in (True, "true", "True")
    first, last = info.get("given_name") or "", info.get("family_name") or ""
    if not (first or last):
        first, last = split_name(info.get("name"))
    return flow, {
        "sub": str(info.get("sub") or ""), "email": (info.get("email") or "").strip().lower(),
        "email_verified": verified or c["trust_email"], "first_name": first, "last_name": last,
    }


def login_or_register(provider, p):
    label = PROVIDERS[provider]["name"]
    if not p["sub"]:
        raise OAuthError(f"{label} did not identify your account.")
    ident = OAuthIdentity.objects.filter(provider=provider, subject=p["sub"]).select_related("user").first()
    if ident:
        if not ident.user.is_active:
            raise OAuthError("This account is deactivated. Please contact HR.")
        return ident.user
    if not p["email"]:
        raise OAuthError(f"Your {label} account did not share an email address.")
    if not p["email_verified"]:
        raise OAuthError(f"Your {label} email address is not verified yet.")
    user = User.objects.filter(email__iexact=p["email"]).first()
    if user:
        if not user.is_active and not user.signup_pending:
            raise OAuthError("This account is deactivated. Please contact HR.")
        user.is_active, user.signup_pending, user.email_verified = True, False, True
        user.save(update_fields=["is_active", "signup_pending", "email_verified"])
    else:
        if not settings.ALLOW_SELF_REGISTRATION:
            raise OAuthError("No Vecta account uses that email. Ask HR to create one for you.")
        if not domain_allowed(p["email"]):
            raise OAuthError(f"Please use your institution email address ({domain_hint()}).")
        user = User(username=unique_username(p["email"]), email=p["email"], first_name=p["first_name"], last_name=p["last_name"],
                    email_verified=True, must_change_password=False)
        user.set_unusable_password()
        user.save()
        alert_hr_new_account(user)
    OAuthIdentity.objects.create(user=user, provider=provider, subject=p["sub"], email=p["email"])
    return user


def link_identity(user, provider, p):
    label = PROVIDERS[provider]["name"]
    if not p["sub"]:
        raise OAuthError(f"{label} did not identify your account.")
    existing = OAuthIdentity.objects.filter(provider=provider, subject=p["sub"]).first()
    if existing:
        if existing.user_id != user.pk:
            raise OAuthError(f"That {label} account is already linked to a different Vecta account.")
        return
    if OAuthIdentity.objects.filter(user=user, provider=provider).exists():
        raise OAuthError(f"A different {label} account is already linked. Disconnect it first.")
    OAuthIdentity.objects.create(user=user, provider=provider, subject=p["sub"], email=p["email"])


def make_exchange_code(flow, user):
    """One-time code the browser trades for a session token (tokens never travel in URLs)."""
    code = secrets.token_urlsafe(32)
    flow.exchange_hash, flow.exchange_user, flow.exchange_expires = _h("oauth:" + code), user, timezone.now() + timedelta(minutes=2)
    flow.save(update_fields=["exchange_hash", "exchange_user", "exchange_expires"])
    return code


def redeem_exchange_code(code):
    flow = OAuthFlow.objects.filter(exchange_hash=_h("oauth:" + (code or "-")), exchange_expires__gt=timezone.now()).select_related("exchange_user").first()
    if not flow:
        raise OAuthError("This sign-in has expired. Please try again.")
    user = flow.exchange_user
    flow.exchange_hash, flow.exchange_user = "", None
    flow.save(update_fields=["exchange_hash", "exchange_user"])
    return user
