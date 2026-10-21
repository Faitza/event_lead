from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", _("Administrateur")
        ORGANIZER = "organizer", _("Organisateur")
        GUEST = "guest", _("Invité")

    email = models.EmailField(_("adresse e-mail"), unique=True)
    role = models.CharField(_("rôle"), max_length=20, choices=Role.choices, default=Role.GUEST)
    phone = models.CharField(_("téléphone"), max_length=30, blank=True)
    avatar = models.ImageField(_("avatar"), upload_to="avatars/", blank=True, null=True)
    # Statut VIP : attribue uniquement apres un paiement "organizer_access" valide.
    is_vip = models.BooleanField(_("organisateur VIP"), default=False)
    vip_since = models.DateTimeField(_("VIP depuis"), null=True, blank=True)
    language = models.CharField(_("langue"), max_length=5, choices=settings.LANGUAGES, blank=True)

    class Meta:
        verbose_name = _("utilisateur")
        verbose_name_plural = _("utilisateurs")

    def __str__(self):
        return self.get_full_name() or self.email or self.username

    @property
    def is_admin_role(self):
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def is_organizer(self):
        return self.role == self.Role.ORGANIZER

    @property
    def is_vip_organizer(self):
        return self.role == self.Role.ORGANIZER and self.is_vip

    @property
    def display_name(self):
        return self.get_full_name() or self.email.split("@")[0]

    @property
    def initials(self):
        name = self.get_full_name() or self.email
        parts = [p for p in name.replace("@", " ").split() if p]
        return "".join(p[0] for p in parts[:2]).upper() or "EL"
