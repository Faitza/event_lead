import uuid
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

PLACEHOLDER_COVERS = [
    "img/photos/event-gala.jpg",
    "img/photos/event-kompa.jpg",
    "img/photos/event-salon.jpg",
    "img/photos/event-chorale.jpg",
]


class EventQuerySet(models.QuerySet):
    def public_active(self):
        return self.filter(event_type=Event.EventType.PUBLIC, status=Event.Status.ACTIVE)

    def upcoming(self):
        return self.filter(date__gte=timezone.localdate())

    def visible_to(self, user):
        """Regle d'acces section 8 : public OU evenement ou l'utilisateur est invite."""
        if user.is_authenticated and user.is_admin_role:
            return self.all()
        if not user.is_authenticated:
            return self.public_active()
        return self.filter(
            Q(event_type=Event.EventType.PUBLIC, status=Event.Status.ACTIVE) | Q(guests__user=user)
        ).exclude(status=Event.Status.DRAFT).distinct()


class EventGroup(models.Model):
    """Regroupe plusieurs événements liés (ex. cérémonie, réception et brunch d'un mariage)."""

    title = models.CharField("titre", max_length=200)
    description = models.TextField("description", blank=True)
    cover_image = models.ImageField("photo de couverture", upload_to="events/groups/", null=True, blank=True)
    created_at = models.DateTimeField("créé le", auto_now_add=True)

    class Meta:
        ordering = ["title"]
        verbose_name = "groupe d'événements"
        verbose_name_plural = "groupes d'événements"

    def __str__(self):
        return self.title

    @property
    def cover_url(self):
        if self.cover_image:
            return self.cover_image.url
        first = self.events.all().first()
        return first.cover_url if first else static(PLACEHOLDER_COVERS[0])


class Event(models.Model):
    class EventType(models.TextChoices):
        PUBLIC = "public", "Public"
        PRIVATE = "private", "Privé"

    class Status(models.TextChoices):
        ACTIVE = "active", "Actif"
        DRAFT = "draft", "Brouillon"
        CANCELLED = "cancelled", "Annulé"

    title = models.CharField("titre", max_length=200)
    event_type = models.CharField("type", max_length=10, choices=EventType.choices, default=EventType.PRIVATE)
    status = models.CharField("statut", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    date = models.DateField("date")
    time = models.TimeField("heure")
    venue = models.CharField("lieu (adresse)", max_length=255)
    latitude = models.FloatField("latitude", null=True, blank=True)
    longitude = models.FloatField("longitude", null=True, blank=True)
    max_guests = models.PositiveIntegerField("nombre maximum d'invités", default=100)
    allow_companions = models.BooleanField("accompagnants autorisés", default=False)
    max_companions = models.PositiveIntegerField("accompagnants maximum par invité", default=0)
    evaluation_delay_days = models.PositiveIntegerField("délai d'évaluation (jours)", default=3)
    description = models.TextField("description", blank=True)
    cover_image = models.ImageField("photo de couverture", upload_to="events/covers/", null=True, blank=True)
    cover_video = models.FileField("vidéo de couverture", upload_to="events/videos/", null=True, blank=True)
    price_htg = models.DecimalField(
        "prix du billet (HTG)", max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Laisser vide si l'événement est gratuit.",
    )
    group = models.ForeignKey(
        EventGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name="events",
        verbose_name="groupe d'événements",
        help_text="Facultatif : regroupe cet événement avec d'autres (cérémonie, réception, brunch...).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="events_created",
        verbose_name="créé par",
    )
    created_at = models.DateTimeField("créé le", auto_now_add=True)

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["date", "time"]
        verbose_name = "événement"
        verbose_name_plural = "événements"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("events:public_detail", args=[self.pk])

    @property
    def is_public(self):
        return self.event_type == self.EventType.PUBLIC

    @property
    def is_past(self):
        return self.date < timezone.localdate()

    @property
    def is_paid(self):
        return bool(self.price_htg)

    @property
    def price_usd(self):
        if self.price_htg is None:
            return None
        return (self.price_htg * settings.HTG_TO_USD_RATE).quantize(self.price_htg.__class__("0.01"))

    @property
    def cover_url(self):
        if self.cover_image:
            return self.cover_image.url
        return static(PLACEHOLDER_COVERS[(self.pk or 0) % len(PLACEHOLDER_COVERS)])

    @property
    def has_location(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def evaluation_opens_on(self):
        return self.date + timedelta(days=self.evaluation_delay_days)

    def stats(self):
        guests = self.guests.all()
        confirmed = guests.filter(status=Guest.Status.CONFIRMED)
        return {
            "total": guests.count(),
            "confirmed": confirmed.count(),
            "declined": guests.filter(status=Guest.Status.DECLINED).count(),
            "maybe": guests.filter(status=Guest.Status.MAYBE).count(),
            "pending": guests.filter(status=Guest.Status.PENDING).count(),
            "companions": confirmed.aggregate(s=models.Sum("companions"))["s"] or 0,
        }


class Guest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        CONFIRMED = "confirmed", "Présent"
        DECLINED = "declined", "Absent"
        MAYBE = "maybe", "Peut-être"

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        WHATSAPP = "whatsapp", "WhatsApp"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="guests", verbose_name="événement")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="invitations", verbose_name="compte lié",
    )
    name = models.CharField("nom", max_length=150)
    email = models.EmailField("email", blank=True)
    phone = models.CharField("téléphone", max_length=30, blank=True)
    status = models.CharField("statut", max_length=10, choices=Status.choices, default=Status.PENDING)
    companions = models.PositiveIntegerField("accompagnants", default=0)
    sent_via = models.CharField("canal d'envoi", max_length=10, choices=Channel.choices, default=Channel.WHATSAPP)
    magic_token = models.UUIDField("lien magique", default=uuid.uuid4, unique=True, editable=False)
    invitation_sent_at = models.DateTimeField("invitation envoyée le", null=True, blank=True)
    replied_at = models.DateTimeField("répondu le", null=True, blank=True)
    wants_gift = models.BooleanField("souhaite offrir un cadeau", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "invité"
        verbose_name_plural = "invités"

    def __str__(self):
        return f"{self.name} ({self.event})"

    def get_invitation_url(self):
        return reverse("events:invitation", args=[self.magic_token])

    @property
    def is_locked(self):
        """Une presence confirmee est definitive (le choix de cadeaux en depend)."""
        return self.status == self.Status.CONFIRMED and self.replied_at is not None

    @property
    def status_badge(self):
        return {
            self.Status.CONFIRMED: "success",
            self.Status.DECLINED: "danger",
            self.Status.MAYBE: "warning",
            self.Status.PENDING: "muted",
        }[self.status]


class EventEvaluation(models.Model):
    """Evaluation post-evenement soumise par un organisateur invite."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="evaluations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="evaluations")
    stars = models.PositiveIntegerField("note", validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField("commentaire", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "user")
        verbose_name = "évaluation"
        verbose_name_plural = "évaluations"

    def __str__(self):
        return f"{self.event} - {self.stars}/5"
