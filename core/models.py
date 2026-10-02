import re

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Review(models.Model):
    name = models.CharField("nom", max_length=100)
    stars = models.PositiveIntegerField("note", validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField("avis")
    is_published = models.BooleanField("publié", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "avis"
        verbose_name_plural = "avis"

    def __str__(self):
        return f"{self.name} ({self.stars}/5)"


class ContactMessage(models.Model):
    name = models.CharField("nom", max_length=100)
    email = models.EmailField("email")
    phone = models.CharField("téléphone", max_length=30, blank=True)
    message = models.TextField("message")
    is_read = models.BooleanField("lu", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "message de contact"
        verbose_name_plural = "messages de contact"

    def __str__(self):
        return f"{self.name} - {self.email}"


class HelpRequest(models.Model):
    """Demande envoyée par le formulaire « J'ai besoin d'aide » et suivie par l'équipe."""

    class Topic(models.TextChoices):
        INVITATION = "invitation", "Mon invitation ou ma réponse"
        GIFT = "gift", "Les cadeaux"
        PAYMENT = "payment", "Un paiement ou un billet"
        VIP = "vip", "L'accès Organisateur VIP"
        ORGANIZE = "organize", "Organiser mon événement"
        OTHER = "other", "Autre question"

    class Status(models.TextChoices):
        NEW = "new", "Nouvelle"
        IN_PROGRESS = "in_progress", "En cours"
        RESOLVED = "resolved", "Résolue"

    name = models.CharField("nom", max_length=100)
    contact = models.CharField("e-mail ou téléphone", max_length=120)
    topic = models.CharField("sujet", max_length=20, choices=Topic.choices, default=Topic.OTHER)
    message = models.TextField("message", max_length=2000)
    status = models.CharField("statut", max_length=20, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField("reçue le", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "demande d'aide"
        verbose_name_plural = "demandes d'aide"

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
