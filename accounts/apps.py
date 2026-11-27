from django.apps import AppConfig
from django.db.models.signals import post_migrate


def create_roles(sender, **kwargs):
    from django.contrib.auth.models import Group

    from .models import Roles

    for name in Roles.STORED:
        Group.objects.get_or_create(name=name)


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        post_migrate.connect(create_roles, sender=self)
        from . import checks, signals  # noqa: F401
