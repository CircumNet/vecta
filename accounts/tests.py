import json
import re
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import Group
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts import oauth
from accounts.models import EmailCode, OAuthFlow, OAuthIdentity, Roles, User, Department
from leave.models import Notification

STRONG = "Maple-River-4821"


def last_code():
    m = re.search(r"code is (\d{6})", mail.outbox[-1].body)
    assert m, mail.outbox[-1].body
    return m.group(1)



class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.c = APIClient()
        self.department = Department.objects.create(
            name="Accounting",
            unit="academic",
        )
        self.hr = User.objects.create_user(
            "hr",
            "hr@gmail.com",
            "pw-Test-12345",
            must_change_password=False,
        )
        self.hr.groups.add(Group.objects.get(name=Roles.HR_MANAGER))
        self.ann = User.objects.create_user(
            "ann",
            "ann@gmail.com",
            "pw-Test-12345",
            first_name="Ann",
            must_change_password=False,
            email_verified=True,
        )
    def post(self, path, data=None, client=None):
        return (client or self.c).post(
            "/api/" + path,
            data or {},
            format="json",
        )
    def signed_in(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c


class RegistrationTests(Base):
    def register(self, email="new@gmail.com", **kw):
        d = {
            "staff_id": "STF-001",
            "first_name": "New",
            "last_name": "Person",
            "email": email,
            "phone": "08012345678",
            "department": "Academic: Accounting",
            "role": "staff",
            "password": STRONG,
        }
        d.update(kw)
        return self.post("auth/register/", d)
    def test_register_creates_active_staff_account_and_allows_login(self):
        r = self.register()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIn("Account created successfully", r.data["detail"])
        u = User.objects.get(email="new@gmail.com")
        self.assertTrue(u.is_active)
        self.assertFalse(u.signup_pending)
        self.assertTrue(u.email_verified)
        self.assertEqual(u.staff_id, "STF-001")
        login = self.post(
            "auth/login/",
            {"identifier": "new@gmail.com", "password": STRONG},
        )
        self.assertEqual(login.status_code, 200, login.data)

        self.assertEqual(
            Notification.objects.filter(user=self.hr, kind="signup").count(),
            1,
        )
    def test_existing_email_is_rejected_without_sending_notice(self):
        r = self.register(email="ann@gmail.com")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            User.objects.filter(email__iexact="ann@gmail.com").count(),
            1,
        )
        self.assertIn("already exists", str(r.data).lower())
        self.assertEqual(len(mail.outbox), 0)
    def test_weak_password_and_domain_rules(self):
        self.assertEqual(self.register(password="12345678").status_code, 400)

        with override_settings(ALLOWED_EMAIL_DOMAINS=[]):
            r = self.register(email="person@yahoo.com")
            self.assertEqual(r.status_code, 201, r.data)
    def test_registration_can_be_switched_off(self):
        with override_settings(ALLOW_SELF_REGISTRATION=False):
            self.assertEqual(self.register().status_code, 403)
            self.assertFalse(
                self.client.get("/api/auth/config/").json()["registration_enabled"]
            )
    def test_deactivated_account_cannot_be_revived_by_registering(self):
        self.ann.is_active = False
        self.ann.save()

        r = self.register(email="ann@gmail.com")
        self.assertEqual(r.status_code, 400)

        self.ann.refresh_from_db()
        self.assertFalse(self.ann.is_active)


class LoginTests(Base):
    def test_login_with_email_or_username_any_case(self):
        for ident in ("ann", "ANN", "ann@gmail.com", "Ann@gmail.com"):
            r = self.post("auth/login/", {"identifier": ident, "password": "pw-Test-12345"})
            self.assertEqual(r.status_code, 200, ident)
        self.assertEqual(r.data["user"]["username"], "ann")
        self.assertEqual(self.post("auth/login/", {"username": "ann", "password": "pw-Test-12345"}).status_code, 200)  # old clients

    def test_failed_logins_lock_the_account_temporarily(self):
        with override_settings(LOGIN_MAX_ATTEMPTS=3):
            for _ in range(3):
                self.assertEqual(self.post("auth/login/", {"identifier": "ann", "password": "nope"}).status_code, 401)
            r = self.post("auth/login/", {"identifier": "ann", "password": "pw-Test-12345"})
            self.assertEqual(r.status_code, 429)
            self.assertIn("Try again in", r.data["detail"])
            User.objects.filter(pk=self.ann.pk).update(locked_until=timezone.now() - timedelta(seconds=1))
            self.assertEqual(self.post("auth/login/", {"identifier": "ann", "password": "pw-Test-12345"}).status_code, 200)

    def test_unknown_user_and_wrong_password_look_the_same(self):
        a = self.post("auth/login/", {"identifier": "ghost", "password": "x"})
        b = self.post("auth/login/", {"identifier": "ann", "password": "x"})
        self.assertEqual((a.status_code, a.data), (b.status_code, b.data))

    def test_expired_api_token_is_rejected_and_deleted(self):
        token = Token.objects.create(user=self.ann)
        Token.objects.filter(pk=token.pk).update(created=timezone.now() - timedelta(days=31))
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        response = client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 401)
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())

    def test_login_records_last_login_and_replaces_old_token(self):
        t1 = self.post("auth/login/", {"identifier": "ann", "password": "pw-Test-12345"}).data["token"]
        t2 = self.post("auth/login/", {"identifier": "ann", "password": "pw-Test-12345"}).data["token"]
        self.assertNotEqual(t1, t2)
        self.assertFalse(Token.objects.filter(key=t1).exists())
        self.ann.refresh_from_db()
        self.assertIsNotNone(self.ann.last_login)


class PasswordResetTests(Base):
    def forgot(self, email="ann@gmail.com"):
        return self.post("auth/password/forgot/", {"email": email})

    def test_full_reset_flow(self):
        t_old = Token.objects.create(user=self.ann)
        self.assertEqual(self.forgot().status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        r = self.post("auth/password/verify/", {"email": "ann@gmail.com", "code": last_code()})
        self.assertEqual(r.status_code, 200, r.data)
        tok = r.data["reset_token"]
        weak = self.post("auth/password/reset/", {"reset_token": tok, "new_password": "password"})
        self.assertEqual(weak.status_code, 400)
        ok = self.post("auth/password/reset/", {"reset_token": tok, "new_password": STRONG})
        self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual(self.post("auth/password/reset/", {"reset_token": tok, "new_password": STRONG + "x"}).status_code, 400)  # single use
        self.assertEqual(self.post("auth/login/", {"identifier": "ann", "password": STRONG}).status_code, 200)
        self.assertFalse(Token.objects.filter(key=t_old.key).exists())
        self.assertIn("password was changed", mail.outbox[-1].subject)

    @mock.patch("accounts.auth_views.emails.send_code", return_value=False)
    def test_mail_provider_failure_is_reported_for_password_reset(self, send_code):
        response = self.forgot()
        self.assertEqual(response.status_code, 503)
        self.assertFalse(EmailCode.objects.filter(purpose=EmailCode.Purpose.RESET,email=self.ann.email,consumed_at__isnull=True,).exists())

    def test_unknown_email_gets_identical_answer_and_no_mail(self):
        known, unknown = self.forgot(), self.forgot("ghost@gmail.com")
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(len(mail.outbox), 1)

    def test_wrong_codes_are_limited_and_cannot_skip_to_reset(self):
        self.forgot()
        good = last_code()
        bad = "000000" if good != "000000" else "111111"
        for _ in range(5):
            self.assertEqual(self.post("auth/password/verify/", {"email": "ann@gmail.com", "code": bad}).status_code, 400)
        self.assertEqual(self.post("auth/password/verify/", {"email": "ann@gmail.com", "code": good}).status_code, 400)
        self.assertEqual(self.post("auth/password/reset/", {"reset_token": "made-up", "new_password": STRONG}).status_code, 400)
  
    def test_password_reset_code_cannot_be_used_for_another_email(self):
        self.post(
            "auth/password/forgot/",
            {"email": "ann@gmail.com"},
        )
        code = last_code()
        r = self.post(
            "auth/password/verify/",
            {"email": "another@gmail.com", "code": code},
        )
        self.assertEqual(r.status_code, 400)

    def test_reset_clears_a_lockout(self):
        User.objects.filter(pk=self.ann.pk).update(locked_until=timezone.now() + timedelta(minutes=9), failed_login_count=2)
        self.forgot()
        tok = self.post("auth/password/verify/", {"email": "ann@gmail.com", "code": last_code()}).data["reset_token"]
        self.post("auth/password/reset/", {"reset_token": tok, "new_password": STRONG})
        self.assertEqual(self.post("auth/login/", {"identifier": "ann", "password": STRONG}).status_code, 200)

    def test_codes_are_hashed_at_rest(self):
        self.forgot()
        self.assertNotIn(last_code(), EmailCode.objects.get().code_hash)


class AccountTests(Base):
    def test_profile_update_and_validation(self):
        c = self.signed_in(self.ann)
        r = c.patch("/api/account/profile/", {"first_name": "Anna", "phone": "0801 234 5678", "email_notifications": False}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.ann.refresh_from_db()
        self.assertEqual((self.ann.first_name, self.ann.phone, self.ann.email_notifications), ("Anna", "0801 234 5678", False))
        self.assertEqual(c.patch("/api/account/profile/", {"first_name": ""}, format="json").status_code, 400)
        r = c.patch("/api/account/profile/", {"department": 1, "is_superuser": True}, format="json")  # HR-managed fields are ignored
        self.assertFalse(User.objects.get(pk=self.ann.pk).is_superuser)

    def test_email_change_needs_password_and_a_code_sent_to_the_new_address(self):
        c = self.signed_in(self.ann)
        body = {"new_email": "ann.new@gmail.com", "password": "wrong"}
        self.assertEqual(c.post("/api/account/email/request/", body, format="json").status_code, 400)
        body["password"] = "pw-Test-12345"
        self.assertEqual(c.post("/api/account/email/request/", body, format="json").status_code, 200)
        self.assertEqual(mail.outbox[-1].to, ["ann.new@gmail.com"])
        self.assertEqual(c.post("/api/account/email/confirm/", {"new_email": "ann.new@gmail.com", "code": "000000" if last_code() != "000000" else "111111"}, format="json").status_code, 400)
        r = c.post("/api/account/email/confirm/", {"new_email": "ann.new@gmail.com", "code": last_code()}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.ann.refresh_from_db()
        self.assertEqual(self.ann.email, "ann.new@gmail.com")
        self.assertEqual(mail.outbox[-1].to, ["ann@gmail.com"])  # the old address is told

    def test_email_change_rejects_taken_addresses_and_someone_elses_code(self):
        c = self.signed_in(self.ann)
        self.assertEqual(c.post("/api/account/email/request/", {"new_email": "HR@gmail.com", "password": "pw-Test-12345"}, format="json").status_code, 400)
        c.post("/api/account/email/request/", {"new_email": "b@gmail.com", "password": "pw-Test-12345"}, format="json")
        code = last_code()
        r = self.signed_in(self.hr).post("/api/account/email/confirm/", {"new_email": "b@gmail.com", "code": code}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_set_password_only_for_accounts_without_one(self):
        c = self.signed_in(self.ann)
        self.assertEqual(c.post("/api/account/password/set/", {"new_password": STRONG}, format="json").status_code, 400)
        self.ann.set_unusable_password()
        self.ann.save()
        self.assertFalse(c.get("/api/account/profile/").data["has_password"])
        self.assertEqual(c.post("/api/auth/change-password/", {"old_password": "x", "new_password": STRONG}, format="json").status_code, 400)
        r = c.post("/api/account/password/set/", {"new_password": STRONG}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.post("auth/login/", {"identifier": "ann", "password": STRONG}).status_code, 200)

    def test_sign_out_other_devices_keeps_this_one(self):
        old = Token.objects.create(user=self.ann)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Token " + old.key)
        new = c.post("/api/account/sessions/revoke/").data["token"]
        self.assertEqual(c.get("/api/auth/me/").status_code, 401)  # the old token died
        c.credentials(HTTP_AUTHORIZATION="Token " + new)
        self.assertEqual(c.get("/api/auth/me/").status_code, 200)

    def test_data_export(self):
        r = self.signed_in(self.ann).get("/api/account/export/")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertEqual(data["profile"]["username"], "ann")
        self.assertIn("leave_requests", data)
        self.assertIn("attachment", r["Content-Disposition"])

    def test_email_preference_suppresses_leave_emails_but_not_in_app_notices(self):
        from leave.services import notify
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            notify(self.ann, "x", "hello")
        self.assertEqual(len(mail.outbox), 1)
        self.ann.email_notifications = False
        self.ann.save()
        with self.captureOnCommitCallbacks(execute=True):
            notify(self.ann, "x", "again")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(Notification.objects.filter(user=self.ann).count(), 2)

    def test_hr_sees_unplaced_signups(self):
        self.ann.department = None
        self.ann.save()
        r = self.signed_in(self.hr).get("/api/users/?needs_setup=1")
        self.assertEqual({u["username"] for u in r.data["results"]}, {"ann"})  # HR itself is not "unplaced"
        self.assertTrue(all(u["needs_setup"] for u in r.data["results"]))


GOOGLE = dict(GOOGLE_CLIENT_ID="cid", GOOGLE_CLIENT_SECRET="sec", SITE_URL="http://testserver")


def profile(sub="g-1", email="new@gmail.com", verified=True, given="Nia", family="Okoro"):
    return {"sub": sub, "email": email, "email_verified": verified, "given_name": given, "family_name": family}


@override_settings(**GOOGLE)
class OAuthTests(Base):
    def start(self, mode="login", client=None):
        r = (client or self.c).post("/api/auth/oauth/google/start/", {"mode": mode}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        return parse_qs(urlparse(r.data["url"]).query), r.data["url"]

    def callback(self, state, info, code="abc"):
        with mock.patch("accounts.oauth.http_post_form", return_value={"access_token": "tok"}) as post, \
             mock.patch("accounts.oauth.http_get_json", return_value=info):
            r = self.client.get("/api/auth/oauth/google/callback/", {"code": code, "state": state})
        self.last_post = post
        return r, parse_qs(urlparse(r["Location"]).query)

    def exchange(self, code):
        return self.post("auth/oauth/exchange/", {"code": code})

    def test_buttons_only_appear_when_configured(self):
        self.assertEqual([p["id"] for p in self.client.get("/api/auth/config/").json()["providers"]], ["google"])
        with override_settings(GOOGLE_CLIENT_ID=""):
            self.assertEqual(self.client.get("/api/auth/config/").json()["providers"], [])
            self.assertEqual(self.post("auth/oauth/google/start/", {}).status_code, 404)

    def test_start_builds_a_correct_authorization_url_with_pkce(self):
        q, url = self.start()
        self.assertTrue(url.startswith("https://accounts.google.com/o/oauth2/v2/auth?"))
        self.assertEqual((q["client_id"], q["response_type"], q["code_challenge_method"]), (["cid"], ["code"], ["S256"]))
        self.assertEqual(q["redirect_uri"], ["http://testserver/api/auth/oauth/google/callback/"])
        self.assertIn("openid", q["scope"][0])
        flow = OAuthFlow.objects.get(state=q["state"][0])
        import base64, hashlib
        want = base64.urlsafe_b64encode(hashlib.sha256(flow.code_verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(q["code_challenge"], [want])

    def test_new_person_signs_up_with_google_and_gets_a_session(self):
        q, _ = self.start()
        r, back = self.callback(q["state"][0], profile())
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("oauth_error", back)
        self.assertEqual(self.last_post.call_args[0][1]["code_verifier"], OAuthFlow.objects.get().code_verifier)
        s = self.exchange(back["oauth_code"][0])
        self.assertEqual(s.status_code, 200, s.data)
        u = User.objects.get(email="new@gmail.com")
        self.assertTrue(u.email_verified and not u.has_usable_password() and u.is_active)
        self.assertEqual((s.data["user"]["has_password"], s.data["user"]["linked_providers"]), (False, ["google"]))
        self.assertEqual(Notification.objects.filter(user=self.hr, kind="signup").count(), 1)
        self.assertEqual(self.exchange(back["oauth_code"][0]).status_code, 400)  # one-time

    def test_returning_user_matched_by_stable_subject_even_if_email_changes(self):
        q, _ = self.start()
        self.callback(q["state"][0], profile())
        q, _ = self.start()
        r, back = self.callback(q["state"][0], profile(email="renamed@gmail.com"))
        self.assertEqual(self.exchange(back["oauth_code"][0]).data["user"]["email"], "new@gmail.com")
        self.assertEqual(User.objects.filter(email__iexact="renamed@gmail.com").count(), 0)

    def test_existing_hr_created_account_is_linked_by_verified_email(self):
        q, _ = self.start()
        r, back = self.callback(q["state"][0], profile(email="ANN@gmail.com"))
        self.assertEqual(self.exchange(back["oauth_code"][0]).data["user"]["username"], "ann")
        self.assertEqual(User.objects.filter(email__iexact="ann@gmail.com").count(), 1)
        self.assertTrue(OAuthIdentity.objects.filter(user=self.ann, provider="google").exists())

    def test_unverified_or_missing_email_is_refused(self):
        for info in (profile(verified=False), profile(email="")):
            q, _ = self.start()
            _, back = self.callback(q["state"][0], info)
            self.assertIn("oauth_error", back)
        self.assertFalse(User.objects.filter(email="new@gmail.com").exists())

    def test_state_is_single_use_and_must_match(self):
        q, _ = self.start()
        _, back = self.callback("forged-state", profile())
        self.assertIn("expired", back["oauth_error"][0])
        _, ok = self.callback(q["state"][0], profile())
        self.assertIn("oauth_code", ok)
        _, replay = self.callback(q["state"][0], profile(sub="g-2", email="other@gmail.com"))
        self.assertIn("oauth_error", replay)
        OAuthFlow.objects.update(expires_at=timezone.now() - timedelta(seconds=1), used_at=None)
        q2, _ = self.start()
        OAuthFlow.objects.filter(state=q2["state"][0]).update(expires_at=timezone.now() - timedelta(seconds=1))
        _, late = self.callback(q2["state"][0], profile(sub="g-3"))
        self.assertIn("oauth_error", late)

    def test_domain_and_registration_rules_apply_to_new_google_accounts_only(self):
        with override_settings(ALLOWED_EMAIL_DOMAINS=["uni.edu"]):
            q, _ = self.start()
            _, back = self.callback(q["state"][0], profile(email="x@gmail.com"))
            self.assertIn("institution email", back["oauth_error"][0])
        with override_settings(ALLOW_SELF_REGISTRATION=False):
            q, _ = self.start()
            _, back = self.callback(q["state"][0], profile(email="x@gmail.com"))
            self.assertIn("Ask HR", back["oauth_error"][0])
            q, _ = self.start()
            _, back = self.callback(q["state"][0], profile(email="ann@gmail.com"))  # existing accounts still work
            self.assertIn("oauth_code", back)

    def test_deactivated_users_cannot_sign_in_with_google(self):
        self.ann.is_active = False
        self.ann.save()
        q, _ = self.start()
        _, back = self.callback(q["state"][0], profile(email="ann@gmail.com"))
        self.assertIn("deactivated", back["oauth_error"][0])

    def test_provider_error_and_cancel_come_back_as_friendly_messages(self):
        r = self.client.get("/api/auth/oauth/google/callback/", {"error": "access_denied"})
        self.assertIn("cancelled", parse_qs(urlparse(r["Location"]).query)["oauth_error"][0])

    def test_link_and_unlink_with_lockout_protection(self):
        c = self.signed_in(self.ann)
        self.assertEqual(self.client.post("/api/auth/oauth/google/start/", {"mode": "link"}, format="json").status_code, 401)
        q, _ = self.start("link", c)
        _, back = self.callback(q["state"][0], profile(sub="g-ann", email="whatever@gmail.com"))
        self.assertEqual(back["oauth_linked"], ["google"])
        self.assertEqual(c.get("/api/account/identities/").data[0]["provider"], "google")
        # a second Vecta account cannot claim the same Google identity
        q, _ = self.start("link", self.signed_in(self.hr))
        _, back = self.callback(q["state"][0], profile(sub="g-ann"))
        self.assertIn("already linked", back["oauth_error"][0])
        # unlink is fine while a password exists, refused when it would lock the person out
        self.ann.set_unusable_password()
        self.ann.save()
        self.assertEqual(c.delete("/api/account/identities/google/").status_code, 400)
        self.ann.set_password(STRONG)
        self.ann.save()
        self.assertEqual(c.delete("/api/account/identities/google/").status_code, 204)

    def test_real_http_code_path_against_a_local_fake_provider(self):
        """Exercises the actual urllib calls (token POST + userinfo GET) instead of mocks."""
        seen = {}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self):
                body = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
                seen["token_form"] = {k: v[0] for k, v in body.items()}
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps({"access_token": "real-token"}).encode())
            def do_GET(self):
                seen["auth"] = self.headers.get("Authorization")
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps(profile(sub="g-http")).encode())

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_port}"
        patched = {**oauth.PROVIDERS, "google": {**oauth.PROVIDERS["google"], "token_url": base + "/token", "userinfo_url": base + "/userinfo"}}
        try:
            with mock.patch.dict(oauth.PROVIDERS, patched):
                q, _ = self.start()
                r = self.client.get("/api/auth/oauth/google/callback/", {"code": "the-code", "state": q["state"][0]})
        finally:
            srv.shutdown()
        back = parse_qs(urlparse(r["Location"]).query)
        self.assertIn("oauth_code", back, back)
        self.assertEqual(seen["auth"], "Bearer real-token")
        self.assertEqual((seen["token_form"]["grant_type"], seen["token_form"]["code"], seen["token_form"]["client_secret"]), ("authorization_code", "the-code", "sec"))
        self.assertTrue(seen["token_form"]["code_verifier"])

    def test_unreachable_provider_is_reported_not_crashed(self):
        patched = {**oauth.PROVIDERS, "google": {**oauth.PROVIDERS["google"], "token_url": "http://127.0.0.1:9/token"}}
        with mock.patch.dict(oauth.PROVIDERS, patched):
            q, _ = self.start()
            r = self.client.get("/api/auth/oauth/google/callback/", {"code": "c", "state": q["state"][0]})
        self.assertIn("Could not reach", parse_qs(urlparse(r["Location"]).query)["oauth_error"][0])

    def test_microsoft_email_is_only_trusted_for_a_pinned_tenant(self):
        with override_settings(MICROSOFT_CLIENT_ID="m", MICROSOFT_CLIENT_SECRET="s", MICROSOFT_TENANT="organizations"):
            self.assertFalse(oauth.conf("microsoft")["trust_email"])
        with override_settings(MICROSOFT_CLIENT_ID="m", MICROSOFT_CLIENT_SECRET="s", MICROSOFT_TENANT="contoso.onmicrosoft.com"):
            c = oauth.conf("microsoft")
            self.assertTrue(c["trust_email"])
            self.assertIn("contoso.onmicrosoft.com", c["auth_url"])


class RobustnessTests(Base):
    def test_unexpected_errors_become_readable_json_with_a_reference(self):
        with mock.patch("accounts.auth_views.User.objects") as m:
            m.filter.side_effect = RuntimeError("boom")
            c = APIClient(raise_request_exception=False)
            r = c.post("/api/auth/login/", {"identifier": "ann", "password": "x"}, format="json")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r["Content-Type"], "application/json")
        self.assertRegex(r.json()["detail"], r"ref [0-9a-f]{8}")
        self.assertEqual(len(r.json()["ref"]), 8)

    def test_registration_does_not_depend_on_sending_verification_email(self):
        body = {
            "staff_id": "STF-FAIL-001",
            "first_name": "A",
            "last_name": "B",
            "email": "mailfail@gmail.com",
            "phone": "08012345678",
            "department": "Academic: Accounting",
            "role": "staff",
            "password": STRONG,
        }
        with mock.patch("accounts.emails.send", return_value=False):
            r = self.post("auth/register/", body)
        self.assertEqual(r.status_code, 201, r.data)
        user = User.objects.get(email="mailfail@gmail.com")
        self.assertTrue(user.is_active)
        self.assertFalse(user.signup_pending)

    def test_schema_check_passes_on_a_healthy_database_and_flags_a_stale_one(self):
        from accounts.checks import database_schema_is_current
        self.assertEqual(database_schema_is_current(None), [])
        real = __import__("django.db", fromlist=["connection"]).connection.introspection.get_table_description

        def stale(cursor, table):
            cols = real(cursor, table)
            return [c for c in cols if not (table == "accounts_user" and c.name == "phone")]

        with mock.patch("django.db.backends.sqlite3.introspection.DatabaseIntrospection.get_table_description", side_effect=stale):
            errs = database_schema_is_current(None)
        self.assertEqual([e.id for e in errs], ["vecta.E001"])
        self.assertIn("phone", errs[0].msg)
        self.assertIn("delete db.sqlite3", errs[0].hint)


class ImportStaffTests(Base):
    CSV = ("first_name,last_name,email,department,job_title,staff_id,department_head,role\n"
        "Chidi,Obi,chidi@uni.edu,Academic: Engineering,Head,E1,yes,staff\n"
        "Amaka,Nwosu,amaka@uni.edu,Academic: Engineering,Lead,E2,,staff\n"
        "Ngozi,Eze,ngozi@uni.edu,Non-academic: People,Officer,H1,,staff\n")

    def run_import(self, text, *flags):
        import tempfile
        from io import StringIO
        from django.core.management import call_command
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(text)
            file_path = f.name
        out, err = StringIO(), StringIO()
        call_command("import_staff", file_path, *flags, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_import_creates_people_units_and_department_heads(self):
        out, _ = self.run_import(self.CSV)
        self.assertIn("Created 3", out)
        chidi, amaka, ngozi = (User.objects.get(email=f"{n}@uni.edu") for n in ("chidi", "amaka", "ngozi"))
        self.assertFalse(chidi.has_usable_password())
        self.assertEqual((amaka.department.name, amaka.department.unit), ("Engineering", "academic"))
        self.assertEqual((ngozi.department.name, ngozi.department.unit), ("People", "non_academic"))
        self.assertEqual(chidi.department.head, chidi)
        self.assertIn("department_head", chidi.roles)
        self.assertNotIn(Roles.HR_MANAGER, ngozi.roles)
        self.assertNotIn(Roles.ADMIN, ngozi.roles)

    def test_imported_people_can_get_in_with_forgot_password(self):
        self.run_import(self.CSV)
        mail.outbox.clear()
        self.post("auth/password/forgot/", {"email": "amaka@uni.edu"})
        tok = self.post("auth/password/verify/", {"email": "amaka@uni.edu", "code": last_code()}).data["reset_token"]
        self.assertEqual(self.post("auth/password/reset/", {"reset_token": tok, "new_password": STRONG}).status_code, 200)
        self.assertEqual(self.post("auth/login/", {"identifier": "amaka@uni.edu", "password": STRONG}).status_code, 200)

    def test_rerun_is_idempotent_and_updates(self):
        self.run_import(self.CSV)
        out, _ = self.run_import(self.CSV.replace("Lead", "Senior Lead"))
        self.assertIn("Created 0 account(s), updated 3", out)
        self.assertEqual(User.objects.filter(email="amaka@uni.edu").count(), 1)
        self.assertEqual(User.objects.get(email="amaka@uni.edu").job_title, "Senior Lead")

    def test_dry_run_changes_nothing(self):
        out, _ = self.run_import(self.CSV, "--dry-run")
        self.assertIn("Would create 3", out)
        self.assertFalse(User.objects.filter(email="chidi@uni.edu").exists())
        self.assertFalse(Department.objects.filter(name="Engineering").exists())

    def test_bad_rows_are_reported_and_nothing_is_imported_unless_skipping(self):
        from django.core.management.base import CommandError
        bad = self.CSV + "X,Y,not-an-email,,,,,\nA,B,ab@uni.edu,,,,yes,\nC,D,cd@uni.edu,,,,,superboss\n"
        with self.assertRaises(CommandError) as cm:
            self.run_import(bad)
        self.assertIn("3 problem(s)", str(cm.exception))
        self.assertFalse(User.objects.filter(email="chidi@uni.edu").exists())
        out, err = self.run_import(bad, "--skip-errors")
        self.assertIn("line 5", err); self.assertIn("line 6", err); self.assertIn("line 7", err)
        self.assertTrue(User.objects.filter(email="chidi@uni.edu").exists())

    def test_csv_cannot_assign_hr_manager_or_admin(self):
        from django.core.management.base import CommandError
        for role in ("hr_manager", "admin"):
            csv_text = (
                "first_name,last_name,email,department,role\n"
                f"Test,Person,{role}@uni.edu,Academic: Engineering,{role}\n"
            )
            with self.assertRaises(CommandError):
                self.run_import(csv_text)
            self.assertFalse(User.objects.filter(email=f"{role}@uni.edu").exists())


# accounts/tests.py — REPLACE the NewAccountNotificationTests class with this:

class NewAccountNotificationTests(Base):
    def register(self, email="new@gmail.com", **kw):
        d = {
            "staff_id": "STF-001",
            "first_name": "New",
            "last_name": "Person",
            "email": email,
            "phone": "08012345678",
            "department": "Academic: Accounting",
            "role": "staff",
            "password": STRONG,
        }
        d.update(kw)
        return self.post("auth/register/", d)

    def run_import(self, text, *flags):
        import tempfile
        from io import StringIO
        from django.core.management import call_command
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(text)
            file_path = f.name
        out, err = StringIO(), StringIO()
        call_command("import_staff", file_path, *flags, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_hr_receives_detailed_notification_on_registration(self):
        Notification.objects.filter(user=self.hr).delete()
        r = self.register(email="newstaff@gmail.com", staff_id="STF-999")
        self.assertEqual(r.status_code, 201)
        
        notif = Notification.objects.filter(user=self.hr, kind="signup").first()
        self.assertIsNotNone(notif)
        self.assertIn("New Person", notif.message)
        self.assertIn("STF-999", notif.message)
        self.assertIn("Accounting", notif.message)

    def test_hr_receives_notification_on_staff_import(self):
        Notification.objects.filter(user=self.hr).delete()
        csv_text = (
            "first_name,last_name,email,department,job_title,staff_id,department_head,role\n"
            "Imported,Person,imported@uni.edu,Academic: Engineering,Head,E1,yes,staff\n"
        )
        self.run_import(csv_text)
        
        # 1 notification per HR user (the batch notification)
        notifs = Notification.objects.filter(user=self.hr, kind="signup")
        self.assertGreaterEqual(notifs.count(), 1, f"Expected ≥1 notification, got {notifs.count()}")
        # The most recent notification should be the batch summary
        latest = notifs.order_by("-created_at").first()
        self.assertIn("1 new staff account", latest.message)