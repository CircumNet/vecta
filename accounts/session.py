from django.contrib.auth.models import update_last_login
from rest_framework.authtoken.models import Token

from .serializers import MeSerializer


def new_token(user):
    """One active token per user; issuing a new one signs every other device out."""
    Token.objects.filter(user=user).delete()
    return Token.objects.create(user=user)


def session_payload(user, touch=True):
    if touch:
        update_last_login(None, user)
    return {"token": new_token(user).key, "must_change_password": user.must_change_password, "user": MeSerializer(user).data}
