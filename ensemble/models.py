"""« Y aller ensemble » : des personnes qui vont au même événement public se trouvent et y vont ensemble.

Règles de sécurité (maquette validée le 20 octobre 2026) :
- réservé aux membres connectés qui confirment avoir 18 ans ou plus et acceptent les règles ;
- on ne voit les autres que si l'on s'est soi-même affiché pour l'événement ;
- on ne peut s'écrire qu'après l'acceptation d'une demande, sans jamais voir le numéro ni l'e-mail ;
- bloquer coupe tout dans les deux sens ; les signalements sont traités dans le tableau de bord.
"""
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

ABOUT_MAX = 200
NOTE_MAX = 300
MESSAGE_MAX = 1000
CHAT_OPEN_DAYS_AFTER = 7       # la conversation se ferme 7 jours après l'événement
WARNING_SHOWN_DAYS = 30        # l'avertissement de l'équipe reste affiché 30 jours


def _photo_path(instance, filename):
    # Nom de fichier impossible à deviner : la photo n'est montrée qu'aux personnes affichées pour le même événement.
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"ensemble/{uuid.uuid4().hex}.{ext}"


class Profile(models.Model):
    """Petit profil montré aux autres personnes affichées pour le même événement."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ensemble_profile")
    first_name = models.CharField(_("prénom affiché"), max_length=40)
    photo = models.ImageField(_("photo"), upload_to=_photo_path, blank=True)
    city = models.CharField(_("ville"), max_length=60)
    about = models.TextField(_("quelques mots"), max_length=ABOUT_MAX, blank=True)
    adult_confirmed_at = models.DateTimeField(_("18 ans ou plus confirmé le"))
    rules_accepted_at = models.DateTimeField(_("règles acceptées le"))
    warned_at = models.DateTimeField(_("averti le"), null=True, blank=True)
    removed_at = models.DateTimeField(_("retiré par l'équipe le"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("petit profil")
        verbose_name_plural = _("petits profils")

    def __str__(self):
        return f"{self.first_name} ({self.user.email})"

    @property
    def initial(self):
        return (self.first_name[:1] or "?").upper()

    @property
    def color(self):
        return (self.pk or 0) % 3

    @property
    def is_removed(self):
        return self.removed_at is not None

    @property
    def show_warning(self):
        return bool(self.warned_at and self.warned_at > timezone.now() - timedelta(days=WARNING_SHOWN_DAYS))


class Listing(models.Model):
    """« Je cherche quelqu'un pour y aller » pour un événement donné."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ensemble_listings")
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="ensemble_listings")
    wants_company = models.BooleanField(_("quelqu'un pour y aller"), default=True)
    wants_transport = models.BooleanField(_("partager le transport"), default=False)
    wants_group = models.BooleanField(_("un groupe d'amis"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "event"], name="ensemble_listing_unique")]
        verbose_name = _("personne affichée")
        verbose_name_plural = _("personnes affichées")

    def __str__(self):
        return f"{self.user} -> {self.event}"


class MeetRequest(models.Model):
    """Demande « Proposer d'y aller ensemble ». Une fois acceptée, elle devient la conversation."""

    class Status(models.TextChoices):
        PENDING = "pending", _("En attente")
        ACCEPTED = "accepted", _("Acceptée")
        DECLINED = "declined", _("Refusée")

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ensemble_sent")
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ensemble_received")
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="ensemble_requests")
    note = models.TextField(_("petit mot"), max_length=NOTE_MAX, blank=True)
    status = models.CharField(_("statut"), max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["sender", "receiver", "event"], name="ensemble_request_unique")]
        indexes = [models.Index(fields=["receiver", "status"], name="ensemble_req_receiver_idx")]
        verbose_name = _("demande")
        verbose_name_plural = _("demandes")

    def __str__(self):
        return f"{self.sender} -> {self.receiver} ({self.event})"

    def other(self, user):
        return self.receiver if user.pk == self.sender_id else self.sender

    def involves(self, user):
        return user.pk in (self.sender_id, self.receiver_id)

    @property
    def chat_closes_on(self):
        return self.event.date + timedelta(days=CHAT_OPEN_DAYS_AFTER)

    @property
    def chat_is_open(self):
        return self.status == self.Status.ACCEPTED and timezone.localdate() <= self.chat_closes_on


class Message(models.Model):
    request = models.ForeignKey(MeetRequest, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    body = models.TextField(_("message"), max_length=MESSAGE_MAX)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("message")
        verbose_name_plural = _("messages")

    def __str__(self):
        return self.body[:40]


class Block(models.Model):
    blocker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ensemble_blocks")
    blocked = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["blocker", "blocked"], name="ensemble_block_unique")]
        verbose_name = _("blocage")
        verbose_name_plural = _("blocages")

    @staticmethod
    def hidden_ids(user):
        """Personnes que `user` a bloquées ou qui l'ont bloqué : elles ne se voient plus et ne peuvent plus s'écrire."""
        pairs = Block.objects.filter(Q(blocker=user) | Q(blocked=user)).values_list("blocker_id", "blocked_id")
        return {a if b == user.pk else b for a, b in pairs}

    @staticmethod
    def between(a, b):
        return Block.objects.filter(Q(blocker=a, blocked=b) | Q(blocker=b, blocked=a)).exists()


class Report(models.Model):
    class Reason(models.TextChoices):
        HARASSMENT = "harassment", _("Messages déplacés ou insistants")
        MONEY = "money", _("Demande d'argent")
        FAKE = "fake", _("Faux profil")
        MINOR = "minor", _("Personne de moins de 18 ans")
        OTHER = "other", _("Autre raison")

    class Status(models.TextChoices):
        NEW = "new", _("À traiter")
        WARNED = "warned", _("Averti")
        REMOVED = "removed", _("Retiré de Y aller ensemble")
        SUSPENDED = "suspended", _("Compte suspendu")
        DISMISSED = "dismissed", _("Classé sans suite")

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ensemble_reports_sent")
    reported = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ensemble_reports")
    event = models.ForeignKey("events.Event", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reason = models.CharField(_("raison"), max_length=20, choices=Reason.choices)
    details = models.TextField(_("explication"), max_length=500, blank=True)
    status = models.CharField(_("statut"), max_length=20, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)
    handled_at = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"], name="ensemble_report_status_idx")]
        verbose_name = _("signalement")
        verbose_name_plural = _("signalements")

    def __str__(self):
        return f"{self.reported} ({self.get_reason_display()})"
