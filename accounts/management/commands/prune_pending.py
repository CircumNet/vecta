import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import EmailCode, OAuthFlow, User


class Command(BaseCommand):
    help = "Delete sign-ups that never verified their email, plus expired codes and OAuth state. Run daily."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=3)

    def handle(self, *args, days, **opts):
        now = timezone.now()
        stale = User.objects.filter(signup_pending=True, date_joined__lt=now - dt.timedelta(days=days))
        n = stale.count()
        stale.delete()
        c = EmailCode.objects.filter(expires_at__lt=now - dt.timedelta(days=1)).delete()[0]
        f = OAuthFlow.objects.filter(expires_at__lt=now - dt.timedelta(hours=1)).delete()[0]
        self.stdout.write(self.style.SUCCESS(f"Removed {n} unverified sign-up(s), {c} old code(s), {f} old OAuth record(s)."))
