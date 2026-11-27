# Vecta

Institutional leave management. Django + Django REST Framework backend with a built-in single-page web app (no build step, no Node needed to run it).

**Going live? Read [DEPLOY.md](DEPLOY.md)** (server setup, HTTPS, email, importing staff, go-live checklist).

Staff request leave → their supervisor (or department head) approves or rejects → HR reviews decisions and reports.

## Quick start

```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo --with-requests           # demo people, policies, holidays and sample activity
python manage.py runserver                           # open http://127.0.0.1:8000
```

Demo logins (password `Passw0rd!123`): `staff1`…`staff7`, `sup.eng`, `head.eng`, `head.fin`, `head.ops`, `hr`, `admin`.
Emails (verification and reset codes) print in the terminal running the server until you configure SMTP.
Django admin: `/admin/`.

> **Upgrading from an earlier build?** The data model changed (accounts, codes, OAuth). Delete `db.sqlite3` and run `migrate` again.

## Accounts

| | |
|---|---|
| **Sign in** | Email *or* username + password. Too many wrong passwords locks the account for 10 minutes. |
| **Register** | Name, email, password → 6-digit code emailed → signed in. Accounts stay inactive until the code is confirmed. New people land as plain staff with no department; **HR is notified** and sees a "Needs setup" badge until they assign a department and supervisor. |
| **Forgot password** | Email → 6-digit code → choose new password. Codes expire after 10 minutes, work once, allow 5 attempts, and can be resent after 60 seconds. The answer is identical whether or not the email exists. Finishing a reset signs out every device and emails a notice. |
| **Google / Microsoft sign-in** | OAuth 2.0 authorization-code flow with PKCE and single-use state. The button appears only when credentials are configured (below). Works for sign-in, sign-up and linking to an existing account. |
| **Account page** | Edit name and phone · change email (code sent to the *new* address) · change or set a password · connect/disconnect Google and Microsoft (refuses to disconnect your last sign-in method) · sign out other devices · email-notification switch · theme · .ics calendar file · download all my data as JSON. |
| **Roles** | `staff` automatic; `hr_manager`/`admin` assigned by an admin; `supervisor`/`department_head` derived from the org structure. |

### Settings that matter (environment variables)

| Variable | Purpose |
|---|---|
| `SITE_URL` | Public base URL, e.g. `https://leave.university.edu`. Used for OAuth redirect URIs. Default `http://127.0.0.1:8000`. |
| `ALLOW_SELF_REGISTRATION` | `1` (default) or `0` to make HR the only way to create accounts. |
| `ALLOWED_EMAIL_DOMAINS` | e.g. `university.edu.ng,staff.university.edu.ng`. Limits self-registration, Google/Microsoft sign-up and email changes. HR-created accounts are not limited. **Recommended in production.** |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` | Use `django.core.mail.backends.smtp.EmailBackend` for real email. |
| `THROTTLE_LOGIN` / `THROTTLE_CODE` / `THROTTLE_REGISTER` | Per-IP rate limits (defaults `10/min`, `30/hour`, `10/hour`). |
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS`, `POSTGRES_*` | Production basics. SQLite is used if `POSTGRES_DB` is unset. |

### Turning on Google sign-in
1. Google Cloud Console → *APIs & Services* → *Credentials* → **Create OAuth client ID** → *Web application*.
2. Authorised redirect URI: `{SITE_URL}/api/auth/oauth/google/callback/` (for local dev: `http://127.0.0.1:8000/api/auth/oauth/google/callback/`).
3. Consent screen scopes: `openid`, `email`, `profile` only.
4. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, restart. The Google button appears on the sign-in and register screens.

### Turning on Microsoft sign-in
1. Microsoft Entra admin centre → *App registrations* → **New registration**, redirect URI type *Web*: `{SITE_URL}/api/auth/oauth/microsoft/callback/`.
2. *Certificates & secrets* → new client secret.
3. Set `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` and **`MICROSOFT_TENANT`** to your institution's tenant id or domain.
   With the default `organizations` value Microsoft's `email` claim is *not trusted* (it can be unverified), so email-matching sign-in is refused; pin your tenant to enable it.

How OAuth identity is matched: a stored provider id (`sub`) first; otherwise a **verified** email matching an existing account links to it; otherwise a new account is created only if registration and the domain rules allow. Deactivated accounts can never sign in this way.

> OAuth was verified with mocked providers and a local fake provider server that exercises the real HTTP code. It has **not** been run against live Google or Microsoft (that needs your credentials), so do one real sign-in after configuring.

## Leave features

| For | Features |
|---|---|
| **Everyone** | Dashboard with balance rings · request form with **live rule checking** · half-day leave · attachments · history timeline · cancel · team calendar (holidays, blackout periods) · notifications bell |
| **Approvers** | Queue with **team-clash warnings** · approve/reject with comments · decided history · **delegation** while away (decisions logged "on behalf of") |
| **HR** | Institution dashboard & charts · all requests with filters · HR review step · reassign approvers · reports with CSV export and print · people & departments · policies, holidays, **blackout periods** · searchable **audit log** |

Rules enforced by the server (`leave/services.py`): balance, overlaps, no past dates, weekends and public holidays excluded, half days, minimum notice and maximum length per leave type, blackout periods (with per-type exemptions), document required for some types, rejection needs a reason, a request can never be decided twice, every action written to an append-only audit trail.

## API overview (token auth: `Authorization: Token <key>`)

| Endpoint | Who |
|---|---|
| `GET /api/auth/config/` · `POST /api/auth/login/` · `logout/` · `me/` · `change-password/` | public / all |
| `POST /api/auth/register/` · `register/verify/` · `register/resend/` | public |
| `POST /api/auth/password/forgot/` · `password/verify/` · `password/reset/` | public |
| `POST /api/auth/oauth/<google\|microsoft>/start/` · `GET …/callback/` · `POST /api/auth/oauth/exchange/` | public (`start` with `mode:"link"` needs a token) |
| `GET/PATCH /api/account/profile/` · `POST account/email/request/` · `account/email/confirm/` · `account/password/set/` · `account/sessions/revoke/` · `GET account/identities/` · `DELETE account/identities/<provider>/` · `GET account/export/` | signed-in user |
| `GET /api/dashboard/` · `me/balances/` · `me/calendar.ics` · `calendar/` · `directory/` | all |
| `POST /api/leave-requests/preview/` · `POST /api/leave-requests/` · `GET …/mine/` · `…/{id}/` · `…/{id}/cancel/` | staff |
| `GET /api/leave-requests/pending-approval/` · `…/decided/` · `POST …/{id}/approve/` · `…/reject/` · `/api/delegations/` | approver / delegate |
| `GET /api/leave-requests/?…` · `POST …/{id}/review/` · `…/reassign/` · `GET /api/reports/leave/?…[&export=csv]` · `GET /api/activity/` | HR |
| `/api/users/` (`?needs_setup=1`) · `/api/departments/` · `/api/leave-types/` · `/api/holidays/` · `/api/blackouts/` | read: all (users: HR) · write: HR |

## Tests

```bash
python manage.py test            # 86 backend tests: rules, permissions, registration, codes, lockout, reset, account, OAuth
```
UI tests load the real front-end modules in jsdom and drive them against a **live** server on a **throw-away database** (sign-in, register with emailed code, forgot password, account management, apply, approve/reject, delegation, HR, forced password change):
```bash
python manage.py migrate && python manage.py seed_demo --with-requests
THROTTLE_LOGIN=1000/min THROTTLE_CODE=1000/min THROTTLE_REGISTER=1000/min \
EMAIL_BACKEND=django.core.mail.backends.filebased.EmailBackend EMAIL_FILE_PATH=sent_emails python manage.py runserver
cd ui-tests && npm install && npm test     # 80 checks; BASE=http://host:port and MAIL_DIR=… if not the defaults
```

## Importing staff
```bash
python manage.py import_staff deploy/staff-import-template.csv --dry-run   # check first, changes nothing
python manage.py import_staff your-staff.csv
```
Sets departments, supervisors, department heads and HR roles from one CSV. Re-running updates people instead of duplicating them. Accounts have no password: people use Google/Microsoft or **Forgot password**.

## Scheduled jobs (cron)
```bash
python manage.py init_balances --year 2027                  # each January; applies carry-over caps
python manage.py remind_pending --days 3 --escalate-after 7 # daily: nudge approvers, escalate, alert HR
python manage.py prune_pending --days 3                     # daily: delete never-verified sign-ups, expired codes and OAuth state
```

Production: `DJANGO_DEBUG=0`, `python manage.py collectstatic`, run with gunicorn behind HTTPS (static files are served by WhiteNoise).

## Project layout
```
config/      settings, urls
accounts/    users, auth (codes.py, oauth.py, emails.py), account management, tests
leave/       models, services.py (all business rules), views, tests, management commands
web/         single-page app: templates/ + static/web/{css,js,logo.svg}  (js/pages/* = one file per screen)
ui-tests/    jsdom end-to-end UI tests
```

## Known limits
- Unexpected server errors return a readable message with a reference (`ref ab12cd34`) that is also in the server log. Starting against a database from an older build stops with `vecta.E001` and tells you what to do.
- One token per user: a new sign-in signs out older sessions; tokens do not expire. Swap in JWT if you need expiry.
- Emails are sent inline; use a task queue (Celery) at scale. Attachments live on local disk outside any public path; use object storage in production.
- Leave cannot span two calendar years. Single approval level with escalation to the department head.
