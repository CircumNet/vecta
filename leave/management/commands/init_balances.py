from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User
from leave.models import LeaveBalance, LeaveType


class Command(BaseCommand):
    help = "Create yearly leave balances for all active users (run each January). Applies carry-over caps."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=timezone.localdate().year)

    def handle(self, *args, year, **opts):
        created = 0
        for user in User.objects.filter(is_active=True):
            for lt in LeaveType.objects.filter(is_active=True):
                if LeaveBalance.objects.filter(user=user, leave_type=lt, year=year).exists():
                    continue
                carry = 0
                if lt.carry_over_cap:
                    prev = LeaveBalance.objects.filter(user=user, leave_type=lt, year=year - 1).first()
                    if prev:
                        carry = max(0, min(prev.available, lt.carry_over_cap))
                LeaveBalance.objects.create(user=user, leave_type=lt, year=year, entitled=lt.default_days + carry)
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Created {created} balance row(s) for {year}."))
