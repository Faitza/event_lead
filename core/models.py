import re

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class Review(models.Model):
    name = models.CharField(_("nom"), max_length=100)
    stars = models.PositiveIntegerField(_("note"), validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField(_("avis"))
    is_published = models.BooleanField(_("publié"), default=False, help_text=_("Un avis envoyé depuis le site attend la validation de l'équipe avant d'apparaître sur l'accueil."))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["is_published", "-created_at"], name="review_published_idx")]
        verbose_name = _("avis")
        verbose_name_plural = _("avis")

    def __str__(self):
        return f"{self.name} ({self.stars}/5)"


class ContactMessage(models.Model):
    name = models.CharField(_("nom"), max_length=100)
    email = models.EmailField(_("email"))
    phone = models.CharField(_("téléphone"), max_length=30, blank=True)
    message = models.TextField(_("message"))
    is_read = models.BooleanField(_("lu"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"], name="contact_created_idx"),
                   models.Index(fields=["is_read"], name="contact_read_idx")]
        verbose_name = _("message de contact")
        verbose_name_plural = _("messages de contact")

    def __str__(self):
        return f"{self.name} - {self.email}"


class HelpRequest(models.Model):
    """Demande envoyée par le formulaire « J'ai besoin d'aide » et suivie par l'équipe."""

    class Topic(models.TextChoices):
        INVITATION = "invitation", _("Mon invitation ou ma réponse")
        GIFT = "gift", _("Les cadeaux")
        PAYMENT = "payment", _("Un paiement ou un billet")
        VIP = "vip", _("L'accès Organisateur VIP")
        ORGANIZE = "organize", _("Organiser mon événement")
        OTHER = "other", _("Autre question")

    class Status(models.TextChoices):
        NEW = "new", _("Nouvelle")
        IN_PROGRESS = "in_progress", _("En cours")
        RESOLVED = "resolved", _("Résolue")

    name = models.CharField(_("nom"), max_length=100)
    contact = models.CharField(_("e-mail ou téléphone"), max_length=120)
    topic = models.CharField(_("sujet"), max_length=20, choices=Topic.choices, default=Topic.OTHER)
    message = models.TextField(_("message"), max_length=2000)
    status = models.CharField(_("statut"), max_length=20, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(_("reçue le"), auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"], name="help_status_created_idx")]
        verbose_name = _("demande d'aide")
        verbose_name_plural = _("demandes d'aide")

    def __str__(self):
        return f"{self.name} - {self.get_topic_display()}"

    @property
    def status_badge(self):
        return {"new": "badge-warning", "in_progress": "badge-primary", "resolved": "badge-success"}[self.status]

    @property
    def contact_is_email(self):
        return "@" in self.contact

    @property
    def whatsapp_number(self):
        """Numéro utilisable avec wa.me (indicatif d'Haïti ajouté aux numéros locaux à 8 chiffres), sinon vide."""
        if self.contact_is_email:
            return ""
        digits = re.sub(r"\D", "", self.contact)
        if len(digits) == 8:
            return "509" + digits
        return digits if 10 <= len(digits) <= 15 else ""
