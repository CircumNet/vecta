# Deploying and rolling out Vecta

This guide takes you from a blank Ubuntu server to a running system that staff can use. It uses PostgreSQL, gunicorn, nginx and free HTTPS. Plan for about an hour.

**What I verified:** gunicorn with production settings, static files, the HTTPS redirect and security headers, registration, per-visitor rate limiting across workers, and the config files' syntax. **What I could not do from here:** provision a real server, send real email, or sign in with real Google/Microsoft accounts. Follow the checklist in section 11 once you are live.

## 0. What you need
- An Ubuntu 22.04 or 24.04 server (1 vCPU / 1 GB RAM is plenty for a few hundred staff) with SSH access.
- A domain name, for example `leave.university.edu.ng`, with an **A record** pointing at the server.
- An email service that can send from your domain (your institution's SMTP, Google Workspace, Microsoft 365, or a transactional provider). Verification and reset codes depend on it.

## 1. Server packages
```bash
sudo apt update && sudo apt install -y python3-venv python3-dev build-essential nginx postgresql certbot python3-certbot-nginx
sudo adduser --system --group --home /srv/vecta vecta
sudo mkdir -p /var/backups/vecta && sudo chown postgres /var/backups/vecta
```

## 2. Database
```bash
sudo -u postgres psql -c "CREATE USER vecta WITH PASSWORD 'choose-a-strong-password';"
sudo -u postgres psql -c "CREATE DATABASE vecta OWNER vecta;"
```

## 3. Code and Python environment
Copy the project to `/srv/vecta/app` (unzip `vecta.zip` and rename the folder, or `git clone` your repository), then:
```bash
sudo chown -R vecta:vecta /srv/vecta
sudo -u vecta python3 -m venv /srv/vecta/venv
sudo -u vecta /srv/vecta/venv/bin/pip install -r /srv/vecta/app/requirements-prod.txt
```

## 4. Configuration
```bash
sudo cp /srv/vecta/app/deploy/env.example /etc/vecta.env
sudo chown root:vecta /etc/vecta.env && sudo chmod 640 /etc/vecta.env
sudo nano /etc/vecta.env
```
Fill in every value (the file explains each). The ones that matter most:

| Setting | Why |
|---|---|
| `DJANGO_SECRET_KEY` | Generate with `python3 -c "import secrets; print(secrets.token_urlsafe(64))"`. Never reuse it or share it. |
| `DJANGO_ALLOWED_HOSTS`, `SITE_URL` | Your domain. A wrong host gives "Bad Request (400)". |
| `POSTGRES_*` | The database from step 2. |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | Without working email nobody can register or reset a password. |
| `ALLOWED_EMAIL_DOMAINS` | Stops outsiders creating accounts. **Set this.** |

## 5. Initialise the database and static files
Run these as the `vecta` user with the environment loaded:
```bash
cd /srv/vecta/app
sudo -u vecta bash -c 'set -a; . /etc/vecta.env; set +a
  /srv/vecta/venv/bin/python manage.py migrate
  /srv/vecta/venv/bin/python manage.py createcachetable      # shared rate-limit counters
  /srv/vecta/venv/bin/python manage.py collectstatic --noinput
  /srv/vecta/venv/bin/python manage.py check --deploy
  /srv/vecta/venv/bin/python manage.py createsuperuser'
```
The superuser is your first **administrator**. Use a real email address. **Do not run `seed_demo` in production.** It creates accounts with a known password.

## 6. Run the app (systemd)
```bash
sudo cp /srv/vecta/app/deploy/vecta.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now vecta
sudo systemctl status vecta        # should say "active (running)"
```

## 7. nginx and HTTPS
```bash
sudo cp /srv/vecta/app/deploy/nginx-vecta.conf /etc/nginx/sites-available/vecta
sudo nano /etc/nginx/sites-available/vecta          # put your domain in server_name
sudo ln -s /etc/nginx/sites-available/vecta /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d leave.university.edu.ng     # free HTTPS certificate, renews itself
```
Open `https://your-domain`. You should see the Vecta sign-in page.

## 8. Email that actually arrives
Codes are useless if they land in spam. Ask whoever runs your email to set up **SPF** and **DKIM** for the sending domain, and send yourself a test:
```bash
sudo -u vecta bash -c 'set -a; . /etc/vecta.env; set +a; cd /srv/vecta/app
  /srv/vecta/venv/bin/python manage.py shell -c "from django.core.mail import send_mail; print(send_mail(\"Vecta test\", \"It works.\", None, [\"you@yourdomain\"]))"'
```
It should print `1`.

## 9. Optional: Google / Microsoft sign-in
Create the OAuth app as described in `README.md`, using the redirect URI `https://your-domain/api/auth/oauth/google/callback/` (or `.../microsoft/callback/`). Put the id and secret in `/etc/vecta.env`, set `MICROSOFT_TENANT` to your tenant, then `sudo systemctl restart vecta`. The buttons appear by themselves. Do one real sign-in to confirm.

## 10. Set up the institution (the "implementation")
1. **Sign in as the administrator.** You will be asked to set a new password first.
2. **People → Staff accounts:** create your **HR manager(s)**, then give them the *HR manager* role (**Roles** button). From here HR can do everything below, and the admin only handles roles.
3. **Policies → Leave types:** set entitlements, notice, maximum length, document rules and carry-over. **Public holidays** and **blackout periods** (exams, year-end close) live on the other tabs.
4. **Add your staff in bulk** instead of one by one. Copy `deploy/staff-import-template.csv`, fill in one row per person, then:
   ```bash
   sudo -u vecta bash -c 'set -a; . /etc/vecta.env; set +a; cd /srv/vecta/app
     /srv/vecta/venv/bin/python manage.py import_staff /path/staff.csv --dry-run   # check first
     /srv/vecta/venv/bin/python manage.py import_staff /path/staff.csv'
   ```
   The file sets departments, who reports to whom (`supervisor_email`), department heads and HR roles. Re-running it updates people instead of duplicating them. Nobody is given a password: staff sign in with Google/Microsoft, or press **Forgot password** and get an emailed code.
5. **Check the org chart.** Every person needs a department or supervisor, otherwise they cannot request leave. HR's dashboard flags anyone who still needs setting up.
6. Tell staff the address. People who register themselves appear as "Needs setup" until HR places them.

**Suggested rollout:** pilot with HR and one department for a week, fix anything odd in policies, then invite everyone.

## 11. Go-live checklist
- [ ] `https://your-domain` loads with a padlock, and `http://` redirects to it
- [ ] `check --deploy` ran (two optional HSTS notes are fine)
- [ ] Test email arrives in an inbox, not spam
- [ ] Registered a test account with a work email and received the code
- [ ] **Forgot password** works end to end
- [ ] Applied for leave as a test staff member and approved it as their supervisor
- [ ] `ALLOWED_EMAIL_DOMAINS` is set; demo data is **not** loaded
- [ ] Backups run (`ls /var/backups/vecta` tomorrow) and you have tried restoring one
- [ ] The attachments folder (`/srv/vecta/app/private_media`) is included in your server backups

## 12. Scheduled jobs and backups
```bash
sudo cp /srv/vecta/app/deploy/vecta.cron /etc/cron.d/vecta
```
This runs reminders and escalation, clears out unverified sign-ups, opens the new year's balances on 2 January, and takes a nightly database backup (kept 30 days).

## 13. Updating to a new version
```bash
# back up first, then replace the code in /srv/vecta/app (keep private_media/)
sudo -u vecta bash -c 'set -a; . /etc/vecta.env; set +a; cd /srv/vecta/app
  /srv/vecta/venv/bin/pip install -r requirements-prod.txt
  /srv/vecta/venv/bin/python manage.py migrate
  /srv/vecta/venv/bin/python manage.py collectstatic --noinput'
sudo systemctl restart vecta
```

## 14. When something goes wrong
| You see | Cause and fix |
|---|---|
| "Something went wrong on our side (ref `ab12cd34`)" | The app caught an unexpected error. Find it: `sudo journalctl -u vecta | grep ab12cd34`. |
| **"Server error"** / `vecta.E001` when starting | The database was made by an **older version**. In development delete `db.sqlite3` and run `migrate`; in production restore the backup taken before the upgrade. |
| "Bad Request (400)" on every page | The domain is missing from `DJANGO_ALLOWED_HOSTS`. |
| 502 Bad Gateway | gunicorn is not running: `systemctl status vecta`, `journalctl -u vecta -n 50`. |
| Page loads but is unstyled | Run `collectstatic` again and restart. |
| "We could not send the verification email" | The `EMAIL_*` settings are wrong, or the provider blocks you. Check `journalctl -u vecta`. |
| "That file is too large" | `client_max_body_size` in nginx is below the 5 MB attachment limit. |
| Everyone gets rate-limited | `NUM_PROXIES`/`BEHIND_PROXY` do not match your setup. With nginx in front, both are `1`. |
| Admin page login fails with CSRF error | `SITE_URL` must be your exact `https://` address. |

## 15. Hosting platforms instead of a server (not tested here)
On Render, Railway or similar: build `pip install -r requirements-prod.txt && python manage.py collectstatic --noinput`; release/pre-deploy `python manage.py migrate && python manage.py createcachetable`; start `gunicorn config.wsgi`; set the same environment variables and a managed PostgreSQL. **Attachments are saved to local disk, which these platforms wipe on redeploy**, so attach a persistent disk mounted at `private_media/` or the uploaded sick notes will disappear.
