import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import timezone

from leave import services
from leave.models import LeaveRequest


class Command(BaseCommand):
    help = "Daily job: remind approvers of stale requests and (optionally) escalate very old ones."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=3, help="Remind after this many days pending")
        parser.add_argument("--escalate-after", type=int, default=0, help="Escalate to the dept head / alert HR after this many days (0 = off)")

    def handle(self, *args, days, escalate_after, **opts):
        cutoff = timezone.now() - dt.timedelta(days=days)
        stale = LeaveRequest.objects.filter(status="pending", created_at__lte=cutoff, current_approver__isnull=False)
        n = 0
        for req in stale.select_related("user", "current_approver"):
            services.notify(
                req.current_approver, "leave_reminder",
                f"Reminder: {req.user.display_name}'s leave request ({req.start_date} to {req.end_date}) is awaiting your decision.", req,
            )
            n += 1
        self.stdout.write(self.style.SUCCESS(f"Sent {n} reminder(s)."))
        if escalate_after:
            escalated, alerted = services.escalate_stale(escalate_after)
            self.stdout.write(self.style.SUCCESS(f"Escalated {escalated} request(s); alerted HR about {alerted}."))
