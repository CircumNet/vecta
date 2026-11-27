import datetime as dt
import random

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Department, Roles, User
from leave import services
from leave.models import BlackoutPeriod, Holiday, LeaveAction, LeaveRequest, LeaveType

PASSWORD = "Passw0rd!123"

LEAVE_TYPES = [  # name, days, doc, paid, carry, notice, max_consecutive, ignore_blackouts
    ("Annual", 20, False, True, 5, 7, 15, False),
    ("Sick", 12, True, True, 0, 0, 0, True),
    ("Maternity", 90, False, True, 0, 30, 0, True),
    ("Paternity", 14, False, True, 0, 14, 0, True),
    ("Study", 10, False, True, 0, 14, 10, False),
    ("Compassionate", 5, False, True, 0, 0, 5, True),
    ("Unpaid", 30, False, False, 0, 14, 20, False),
]

HOLIDAYS = {(1, 1): "New Year's Day", (5, 1): "Workers' Day", (6, 12): "Democracy Day",
            (10, 1): "Independence Day", (12, 25): "Christmas Day", (12, 26): "Boxing Day"}

# --- ALL DEPARTMENTS FROM FRONTEND ---
ACADEMIC_DEPTS = [
    "Accounting", 
    "Banking and Finance", 
    "Biochemistry", 
    "Business Admin", 
    "Computer Science", 
    "Cybersecurity", 
    "Data Science", 
    "Economics", 
    "Law", 
    "Mass Communication", 
    "Microbiology", 
    "Nursing", 
    "Philosophy", 
    "Public Admin", 
    "Religious Studies"
]

NON_ACADEMIC_DEPTS = [
    "Admin", 
    "Bursary", 
    "Human Resources", 
    "Works"
]

# Demo users assigned to some of the real departments
USERS = [  # username, first, last, dept, title
    ("head.eng", "Chidi", "Obi", "Computer Science", "Head of Computer Science"),
    ("staff1", "Tunde", "Bello", "Computer Science", "Software Engineer"),
    ("staff2", "Zainab", "Musa", "Cybersecurity", "QA Engineer"),
    ("staff3", "Ifeanyi", "Okafor", "Data Science", "DevOps Engineer"),
    ("head.fin", "Bola", "Adeyemi", "Accounting", "Head of Accounting"),
    ("staff4", "Kemi", "Lawal", "Accounting", "Accountant"),
    ("staff5", "Emeka", "Eze", "Banking and Finance", "Payroll Officer"),
    ("head.ops", "Yusuf", "Danjuma", "Works", "Head of Works"),
    ("staff6", "Funke", "Adebayo", "Admin", "Logistics Officer"),
    ("staff7", "Segun", "Balogun", "Bursary", "Facilities Officer"),
    ("hr", "Ngozi", "Eze", "Human Resources", "HR Manager"),
]


class Command(BaseCommand):
    help = "Create demo departments, users, leave types and holidays (development only). Add --with-requests for sample activity."

    def add_arguments(self, parser):
        parser.add_argument("--with-requests", action="store_true", help="Also create historical and live sample requests")

    def handle(self, *args, with_requests=False, **opts):
        today = timezone.localdate()
        year = today.year

        # 1. Create Leave Types
        for name, days, doc, paid, carry, notice, maxc, ign in LEAVE_TYPES:
            LeaveType.objects.get_or_create(name=name, defaults=dict(
                default_days=days, requires_document=doc, is_paid=paid, carry_over_cap=carry,
                min_notice_days=notice, max_consecutive_days=maxc, ignore_blackouts=ign))

        # 2. Create Holidays
        for y in (year, year + 1):
            for (m, d), name in HOLIDAYS.items():
                Holiday.objects.get_or_create(date=dt.date(y, m, d), defaults={"name": name})

        # 3. Create ALL Departments (matching the frontend exactly)
        depts = {}
        for name in ACADEMIC_DEPTS:
            d, _ = Department.objects.get_or_create(name=name, defaults={"unit": "academic"})
            depts[name] = d
        for name in NON_ACADEMIC_DEPTS:
            d, _ = Department.objects.get_or_create(name=name, defaults={"unit": "non_academic"})
            depts[name] = d

        # 4. Create Demo Users
        users = {}
        for username, first, last, dept_name, title in USERS:
            u, created = User.objects.get_or_create(username=username, defaults=dict(
                first_name=first, last_name=last, email=f"{username}@example.com", department=depts[dept_name],
                job_title=title, must_change_password=False, email_verified=True))
            if created:
                u.set_password(PASSWORD)
                u.save()
            users[username] = u

        # Assign HODs to their departments
        for dept_name, head in (("Computer Science", "head.eng"), ("Accounting", "head.fin"), ("Works", "head.ops"), ("Human Resources", "hr")):
            depts[dept_name].head = users[head]
            depts[dept_name].save()

        # Assign Roles
        users["hr"].groups.add(Group.objects.get(name=Roles.HR_MANAGER))
        
        admin, created = User.objects.get_or_create(username="admin", defaults=dict(
            first_name="System", last_name="Admin", email="admin@example.com", must_change_password=False, is_staff=True, email_verified=True))
        if created:
            admin.set_password(PASSWORD)
            admin.save()
        admin.groups.add(Group.objects.get(name=Roles.ADMIN))

        # Create a Blackout period
        BlackoutPeriod.objects.get_or_create(
            name="Year-end financial close", start_date=dt.date(year, 12, 14), end_date=dt.date(year, 12, 31),
            defaults=dict(department=depts["Accounting"], reason="Finance team is needed for year-end reporting"))

        if with_requests:
            self.sample_requests(users, today)

        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready. Logins (password {PASSWORD}): staff1..staff7, head.eng, head.fin, head.ops, hr, admin"))

    def sample_requests(self, users, today):
        if LeaveRequest.objects.exists():
            self.stdout.write("Requests already exist; skipping samples.")
            return
        rnd = random.Random(7)
        annual, sick = LeaveType.objects.get(name="Annual"), LeaveType.objects.get(name="Sick")
        staff = [u for u in users.values() if u.username.startswith("staff")]
        hr = users["hr"]

        # History: approved leave spread over earlier months of this year.
        year_start = dt.date(today.year, 1, 1)
        taken = {u.pk: [] for u in staff}
        annual_used = {u.pk: 0 for u in staff}
        for _ in range(26):
            u = rnd.choice(staff)
            span = (today - dt.timedelta(days=10) - year_start).days
            if span < 14:
                break
            start = year_start + dt.timedelta(days=rnd.randrange(span))
            start += dt.timedelta(days=(7 - start.weekday()) % 7)
            end = start + dt.timedelta(days=rnd.choice([0, 1, 2, 4, 4, 9]))
            if end >= today - dt.timedelta(days=3) or end.year != start.year:
                continue
            if any(s <= end and start <= e for s, e in taken[u.pk]):
                continue
            lt = rnd.choices([annual, sick], weights=[4, 1])[0]
            days = services.count_working_days(start, end)
            if days == 0:
                continue
            if lt == annual and annual_used[u.pk] + days > 8:
                continue
            annual_used[u.pk] += days if lt == annual else 0
            taken[u.pk].append((start, end))
            approver = u.department.head
            decided = timezone.make_aware(dt.datetime.combine(start - dt.timedelta(days=rnd.randint(2, 9)), dt.time(10, 0)))
            req = LeaveRequest.objects.create(
                user=u, leave_type=lt, start_date=start, end_date=end, working_days=days, status="approved",
                current_approver=approver, decided_by=approver, decided_at=decided,
                hr_reviewed_by=hr if rnd.random() < 0.8 else None)
            if req.hr_reviewed_by:
                req.hr_reviewed_at, req.hr_note = decided + dt.timedelta(days=1), "Verified"
                req.save(update_fields=["hr_reviewed_at", "hr_note"])
            LeaveRequest.objects.filter(pk=req.pk).update(created_at=decided - dt.timedelta(days=1))
            for action, actor, when in (("submitted", u, decided - dt.timedelta(days=1)), ("approved", approver, decided)):
                a = LeaveAction.objects.create(leave_request=req, actor=actor, action=action)
                LeaveAction.objects.filter(pk=a.pk).update(created_at=when)
            bal = services._get_balance(u, lt, start.year)
            bal.used += days
            bal.save(update_fields=["used"])


        away_start = today - dt.timedelta(days=1)
        away = users["staff7"]
        req = LeaveRequest.objects.create(
            user=away, leave_type=annual, start_date=away_start, end_date=today + dt.timedelta(days=3),
            working_days=services.count_working_days(away_start, today + dt.timedelta(days=3)), status="approved",
            current_approver=users["head.ops"], decided_by=users["head.ops"], decided_at=timezone.now() - dt.timedelta(days=9))
        LeaveAction.objects.create(leave_request=req, actor=away, action="submitted")
        LeaveAction.objects.create(leave_request=req, actor=users["head.ops"], action="approved")

        # Live requests through the real workflow.
        monday = today + dt.timedelta(days=21)
        monday += dt.timedelta(days=(7 - monday.weekday()) % 7)
        if monday.year != (monday + dt.timedelta(days=4)).year:
            monday += dt.timedelta(days=14)

        def apply(user, start, end, lt=annual, reason="", part="full"):
            try:
                return services.submit_leave(user=user, leave_type=lt, start_date=start, end_date=end, reason=reason, day_part=part)
            except Exception as exc:
                self.stdout.write(f"  skipped sample request for {user.username}: {exc}")

        r1 = apply(users["staff1"], monday, monday + dt.timedelta(days=4), reason="Family trip")
        if r1:
            services.approve(r1, users["head.eng"], "Enjoy! Handover notes please.")
        apply(users["staff2"], monday + dt.timedelta(days=7), monday + dt.timedelta(days=11), reason="Wedding")
        apply(users["staff3"], monday + dt.timedelta(days=9), monday + dt.timedelta(days=11), reason="Moving house")
        apply(users["staff5"], monday + dt.timedelta(days=14), monday + dt.timedelta(days=14), reason="Dentist", part="morning")
        r4 = apply(users["staff4"], monday + dt.timedelta(days=2), monday + dt.timedelta(days=6), reason="Short break")
        if r4:
            services.reject(r4, users["head.fin"], "Month-end close; please pick another week.")
