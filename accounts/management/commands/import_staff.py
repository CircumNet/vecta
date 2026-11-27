import csv

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction
from leave.services import notify
from django.db.models import Q
from accounts.models import Department, Roles, User
from accounts.signup import unique_username

TRUE = {"1", "true", "yes", "y", "x"}
COLUMNS = "first_name, last_name, email, department, job_title, staff_id, department_head"

class Command(BaseCommand):
    help = (
        "Bulk-create or update staff from a CSV file.\n"
        f"Columns: {COLUMNS}  (only first_name, last_name and email are required).\n"
        "Accounts get NO password: people sign in with Google/Microsoft or use 'Forgot password' (a code is emailed)."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", help="CSV file (UTF-8)")
        parser.add_argument("--dry-run", action="store_true", help="Check everything and report, but change nothing")
        parser.add_argument("--skip-errors", action="store_true", help="Import the good rows even if some rows have problems")

    def handle(self, *args, path, dry_run, skip_errors, **opts):
        try:
            with open(path, encoding="utf-8-sig", newline="") as fh:
                rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]
        except OSError as exc:
            raise CommandError(f"Cannot read {path}: {exc}")
        if not rows:
            raise CommandError("The file has no rows.")
        errors, created, updated, staged = [], 0, 0, []

        with transaction.atomic():
            # pass 1: people and departments
            for n, r in enumerate(rows, start=2):
                email = r.get("email", "").lower()
                try:
                    if not (r.get("first_name") and r.get("last_name") and email):
                        raise ValueError("first_name, last_name and email are required")
                    try:
                        validate_email(email)
                    except ValidationError:
                        raise ValueError(f"'{email}' is not a valid email address")
                    role = r.get("role", "").strip().lower()
                    if role and role != Roles.STAFF:
                        raise ValueError(
                            "CSV imports can only create Staff accounts; "
                            "HR Manager and Admin roles must be assigned through the approved process"
                        )
                    user = User.objects.filter(email__iexact=email).first()
                    sid = r.get("staff_id") or None
                    if sid and User.objects.filter(staff_id=sid).exclude(pk=user.pk if user else None).exists():
                        raise ValueError(f"staff_id '{sid}' belongs to someone else")
                    dept = None
                    department_value = r.get("department", "").strip()
                    if department_value:
                        unit = "academic"  # Unprefixed legacy values default to Academic.
                        department_name = department_value
                        if ":" in department_value:
                            prefix, department_name = department_value.split(":", 1)
                            prefix = prefix.strip().lower().replace("-", "_").replace(" ", "_")
                            if prefix not in {"academic", "non_academic"}:
                                raise ValueError(
                                    f"unknown department unit '{prefix}'; use 'Academic: Name' "
                                    "or 'Non-academic: Name'"
                                )
                            unit = prefix
                            department_name = department_name.strip()
                        if not department_name:
                            raise ValueError("department name cannot be empty")
                        dept, _ = Department.objects.get_or_create(
                            name=department_name,
                            defaults={"unit": unit},
                        )
                        if dept.unit != unit:
                            raise ValueError(
                                f"department '{department_name}' already exists as "
                                f"'{dept.get_unit_display()}'; the CSV specifies a different unit"
                            )
                    if user:
                        updated += 1
                    else:
                        user = User(username=unique_username(email), email=email, must_change_password=False)
                        user.set_unusable_password()
                        created += 1
                    user.first_name, user.last_name = r["first_name"], r["last_name"]
                    if dept:
                        user.department = dept
                    if r.get("job_title"):
                        user.job_title = r["job_title"]
                    if sid:
                        user.staff_id = sid
                    user.save()
                    staged.append((n, user, r, dept))
                except ValueError as exc:
                    errors.append(f"line {n}: {exc}")

            # pass 2: department heads (everyone exists now)
            for n, user, r, dept in staged:
                try:
                    if r.get("department_head", "").lower() in TRUE:
                        if not dept:
                            raise ValueError("department_head is set but department is empty")
                        dept.head = user
                        dept.save(update_fields=["head"])
                except ValueError as exc:
                    errors.append(f"line {n}: {exc}")

            if errors and not skip_errors:
                transaction.set_rollback(True)
            elif dry_run:
                transaction.set_rollback(True)

        for e in errors[:50]:
            self.stderr.write(self.style.ERROR(e))
        if errors and not skip_errors:
            raise CommandError(f"{len(errors)} problem(s) found. Nothing was imported. Fix the file, or use --skip-errors to import the good rows.")
        verb = "Would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(f"{verb} {created} account(s), updated {updated}." + (f" {len(errors)} row(s) skipped." if errors else "")))
        if not dry_run:
            self.stdout.write("People can now sign in with Google/Microsoft, or choose 'Forgot password' to get an emailed code.")
        
        # After all users have been created/updated:
        if created > 0:
            hr_users = User.objects.filter(is_active=True).filter(
                Q(groups__name__in=[Roles.HR_MANAGER, Roles.ADMIN]) | Q(is_superuser=True)
            ).distinct()
            message = f"{created} new staff account(s) imported. Please review their details."
            for h in hr_users:
                notify(h, "signup", message)
