# Vecta on Render (free demo)

## Important limitations
Render Free web services sleep after inactivity and have an ephemeral filesystem. Free Render Postgres expires after 30 days and does not include backups. Do not use this free setup for real HR records or sensitive leave attachments. Uploaded files under `private_media/` can disappear on restart/redeploy. Use only synthetic test data until you move to persistent paid storage/hosting and establish backups.

## Deploy
1. Push the contents of this `vecta` folder to a GitHub repository. Keep `render.yaml`, `build.sh`, `manage.py`, `config/`, `accounts/`, `leave/`, and `web/` at the repository root (not inside another nested `vecta/` directory).
2. In Render, choose **New → Blueprint**, connect the GitHub repository, and apply the `render.yaml` blueprint. It creates a free web service and free PostgreSQL database.
3. The blueprint's default URL is `https://vecta-demo.onrender.com`. If Render assigns a different URL because the name is unavailable, update `SITE_URL` and `DJANGO_ALLOWED_HOSTS` in the Render service environment to match the actual hostname, then redeploy.
4. Set `EMAIL_HOST_PASSWORD` to your email provider's credential/API SMTP key and `DEFAULT_FROM_EMAIL` to a sender address verified with that provider. The example uses SendGrid SMTP on port 2525 because Render blocks outbound SMTP ports 25, 465, and 587 on free web services. Check provider availability, account verification, and current limits. Never commit email secrets to GitHub.
5. In Render, open the service's **Shell** if available on your plan and run `python manage.py createsuperuser`. If shell access is unavailable on the free service, create a one-off admin bootstrap command locally only if you understand how to run it securely; do not expose a public admin-creation endpoint. You can alternatively temporarily use a local clone connected to the database only if you can securely obtain the database connection details.
6. Test the home page, sign-in, email verification, password reset, and a test leave workflow using synthetic data only.

## Environment settings
The blueprint generates `DJANGO_SECRET_KEY` and connects `DATABASE_URL`. Configure the sender credentials in Render's Environment page. Restrict `ALLOWED_EMAIL_DOMAINS` to your institution's real domain before enabling self-registration for real users.
