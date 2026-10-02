from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Authentification par adresse email (insensible a la casse) + mot de passe."""

    def authenticate(self, request, email=None, password=None, **kwargs):
        if email is None or password is None:
            return None
        User = get_user_model()
        try:
            user = User.objects.get(email__iexact=email.strip())
        except User.DoesNotExist:
            User().set_password(password)  # limite les attaques par mesure du temps
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
