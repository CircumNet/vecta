# Vecta targeted fixes

This package contains targeted changes only for the ten issue areas discussed. No framework migration, redesign, or unrelated feature work was performed.

## Application changes

1. **Staff directory scope** — `leave/views_extra.py`: non-HR users are now restricted to their own department even when they use the search parameter. Only HR can search the institution-wide directory.
2. **Token/session lifetime** — `accounts/authentication.py`, `config/settings.py`: API tokens now expire after `TOKEN_TTL_DAYS` (default 30 days) and expired tokens are deleted. This does not remove the existing browser `localStorage` token storage; a full HttpOnly-cookie migration remains a separate security change because it affects every login, OAuth, password, and API request flow.
3. **Upload validation** — `leave/services.py`: supporting documents must match the file signature for PDF, JPEG, or PNG, in addition to the existing extension and 5 MB checks.
4. **Self-registration restriction** — `config/settings.py`, `render.yaml`: production startup now requires `ALLOWED_EMAIL_DOMAINS` when self-registration is enabled. The Render blueprint now prompts for that value instead of silently leaving it empty.
5. **Read-only leave preview** — `leave/services.py`: preview no longer creates missing leave-balance rows.
6. **Authentication lifecycle** — same token-expiry change above; expired credentials are rejected and removed.
7. **Pagination and concurrent submissions** — `web/static/web/js/api.js`: `listAll()` now follows pagination until the API has no next page. `leave/services.py`: leave submissions lock the employee row before checking overlaps, preventing parallel requests for different leave types from bypassing the overlap check on databases that support row-level locks.
8. **Verification/reset email handling** — `accounts/auth_views.py`, `accounts/emails.py`: password-reset now reports provider delivery failures, removes the unusable code, and email sending reports success only when Django reports one message sent. Registration already had delivery-failure handling; it benefits from the corrected shared mail result.
9. **Sidebar collapse** — `web/static/web/js/app.js`, `web/static/web/css/app.css`: the hamburger now collapses and restores the desktop sidebar as well as retaining the mobile drawer behaviour.
10. **Leave-calendar privacy** — `leave/views_extra.py`: staffs see only their own leave; department heads see leave in departments they head; HR sees institution-wide leave. Query-string filters cannot widen a non-HR user's access.

## Tests added or updated

- `leave/tests.py`: calendar role visibility, cross-department directory search, mismatched upload signatures, and read-only preview behaviour.
- `accounts/tests.py`: password-reset delivery failure and expired-token rejection.

## Required deployment actions

1. In Render, set `ALLOWED_EMAIL_DOMAINS` to the institution's real email domain(s), e.g. `university.edu.ng`. Multiple domains can be comma-separated. If public registration is not wanted, set `ALLOW_SELF_REGISTRATION=0` instead.
2. In Render, set `EMAIL_HOST_PASSWORD` to the SMTP provider credential/API key and `DEFAULT_FROM_EMAIL` to a sender address verified by that provider. The current blueprint uses SendGrid SMTP on port 2525. Confirm the SendGrid sender/domain is verified and that the key has mail-send permission.
3. Keep `TOKEN_TTL_DAYS=30` or choose a different positive number of days. Users will need to sign in again after token expiry.
4. Deploy the updated code and check Render logs for SMTP errors. In local development, the default email backend is the console backend, so messages appear in the server terminal rather than being delivered to an inbox unless SMTP settings are configured.

## Verification limitations

Python compilation and JavaScript syntax checks passed in the editing environment. The Django test suite could not be executed because Django/DRF are not installed and package installation was unavailable in this environment. Run `python manage.py test` in the project's normal environment before deploying.


## Brevo and personal email deployment configuration

- Render SMTP defaults are configured for Brevo (`smtp-relay.brevo.com`, port `587`, TLS enabled).
- Set `EMAIL_HOST_USER` to the SMTP login shown in Brevo and `EMAIL_HOST_PASSWORD` to the generated SMTP key.
- Set `DEFAULT_FROM_EMAIL` to the exact sender address verified in Brevo.
- `ALLOWED_EMAIL_DOMAINS` is optional: leave it unset or empty to allow any valid personal email domain. Set `ALLOW_SELF_REGISTRATION=1` to allow registration, while keeping email verification enabled.
- A free Gmail sender may show DKIM/DMARC warnings in Brevo; use it for initial testing only if Brevo permits sending. A domain you control with SPF/DKIM/DMARC authentication is recommended for reliable production delivery.
