from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Roles, User


@receiver(post_save, sender=User)
def give_new_users_the_staff_role(sender, instance, created, **kwargs):
    if created:
        group, _ = Group.objects.get_or_create(name=Roles.STAFF)
        instance.groups.add(group)
