import os
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext, gettext_noop
from django.utils.translation import gettext_lazy as _

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


# Catégories proposées par défaut (nom, icône) : les noms sont listés ici pour être traduits (le site affiche `label`).
# Elles forment les tuiles « Pour chaque occasion » de l'accueil, dans cet ordre.
DEFAULT_CATEGORIES = [
    (gettext_noop("Anniversaire"), "bi-balloon"), (gettext_noop("Mariage"), "bi-heart"),
    (gettext_noop("Baby shower"), "bi-balloon-heart"), (gettext_noop("Baptême"), "bi-droplet"),
    (gettext_noop("Gala"), "bi-stars"), (gettext_noop("Conférence"), "bi-mic"),
    (gettext_noop("Concert"), "bi-music-note-beamed"),
]


class EventCategory(models.Model):
    """Catégorie d'événement (mariage, gala, concert...), utilisée pour filtrer les listes publiques."""

    name = models.CharField(_("nom"), max_length=60, unique=True)
    slug = models.SlugField(_("identifiant dans l'adresse"), max_length=70, unique=True, blank=True)
    icon_name = models.CharField(_("icône"), max_length=50, default="bi-calendar2-event")
    order = models.PositiveSmallIntegerField(_("ordre d'affichage"), default=0)
    image = models.ImageField(_("photo de la tuile"), upload_to="categories/", blank=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = _("catégorie d'événements")
        verbose_name_plural = _("catégories d'événements")

    def __str__(self):
        return self.name

    @property
    def label(self):
        """Nom affiché : traduit pour les catégories par défaut, tel quel pour celles créées par l'équipe."""
        return gettext(self.name)

    @classmethod
    def missing_defaults(cls):
        """Catégories par défaut qui n'existent pas encore (liste de (nom, icône))."""
        existing = {name.lower() for name in cls.objects.values_list("name", flat=True)}
        return [(name, icon) for name, icon in DEFAULT_CATEGORIES if name.lower() not in existing]

    @classmethod
    def add_missing_defaults(cls):
        """Crée les catégories par défaut absentes, à la suite des autres. Renvoie le nombre créé."""
        last = cls.objects.order_by("-order").values_list("order", flat=True).first() or 0
        created = 0
        for name, icon in cls.missing_defaults():
            last += 1
            cls.objects.create(name=name, icon_name=icon, order=last)
            created += 1
        return created

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "categorie"
            slug, n = base, 2
            while EventCategory.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*args, **kwargs)


class Event(models.Model):
    class EventType(models.TextChoices):
        PUBLIC = "public", _("Public")
        PRIVATE = "private", _("Privé")

    class Status(models.TextChoices):
        ACTIVE = "active", _("Actif")
        DRAFT = "draft", _("Brouillon")
        CANCELLED = "cancelled", _("Annulé")

    title = models.CharField(_("titre"), max_length=200)
    event_type = models.CharField(_("type"), max_length=10, choices=EventType.choices, default=EventType.PRIVATE)
    status = models.CharField(_("statut"), max_length=10, choices=Status.choices, default=Status.ACTIVE)
    date = models.DateField(_("date"))
    time = models.TimeField(_("heure"))
    venue = models.CharField(_("lieu (adresse)"), max_length=255)
    latitude = models.FloatField(_("latitude"), null=True, blank=True)
    longitude = models.FloatField(_("longitude"), null=True, blank=True)
    max_guests = models.PositiveIntegerField(_("nombre maximum d'invités"), default=100)
    allow_companions = models.BooleanField(_("accompagnants autorisés"), default=False)
    max_companions = models.PositiveIntegerField(_("accompagnants maximum par invité"), default=0)
    evaluation_delay_days = models.PositiveIntegerField(_("délai d'évaluation (jours)"), default=3)
    # Relances des invités sans réponse (WhatsApp ou e-mail, jamais SMS) : au plus 3 par invité
    reminder_first_after_days = models.PositiveSmallIntegerField(_("première relance après (jours)"), default=3)
    reminder_every_days = models.PositiveSmallIntegerField(_("puis tous les (jours)"), default=7)
    reminder_max = models.PositiveSmallIntegerField(_("relances maximum par invité"), default=3)
    reminder_hour = models.PositiveSmallIntegerField(_("heure d'envoi des relances"), default=10)
    reminders_auto = models.BooleanField(_("envoi automatique des relances par e-mail"), default=False)
    accept_contributions = models.BooleanField(
        _("accepter les contributions en argent"), default=False,
        help_text=_("Les invités peuvent contribuer en argent (MonCash ou NatCash) à la place d'un cadeau."),
    )
    thanks_message = models.TextField(_("message de remerciement"), blank=True)
    thanks_published_at = models.DateTimeField(_("remerciements publiés le"), null=True, blank=True)
    description = models.TextField(_("description"), blank=True)
    cover_image = models.ImageField(_("photo de couverture"), upload_to="events/covers/", null=True, blank=True)
    cover_video = models.FileField(_("vidéo de couverture"), upload_to="events/videos/", null=True, blank=True)
    price_htg = models.DecimalField(
        _("prix du billet (HTG)"), max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=_("Laisser vide si l'événement est gratuit."),
    )
    category = models.ForeignKey(
        EventCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="events",
        verbose_name=_("catégorie"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="events_created",
        verbose_name=_("créé par"),
    )
    created_at = models.DateTimeField(_("créé le"), auto_now_add=True)

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["date", "time"]
        verbose_name = _("événement")
        verbose_name_plural = _("événements")

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
    def has_gift_step(self):
        """L'invité qui confirme voit l'étape « cadeau » : une liste de cadeaux ou la contribution en argent."""
        return self.accept_contributions or self.gifts.exists()

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


ENTRY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans I, O, 0 et 1 : faciles à relire à voix haute


def new_entry_code():
    """Code d'entrée de l'invité, par exemple EL-7K4Q-92MD : il est dans le QR code et se saisit à la main."""
    def pick(n):
        return "".join(secrets.choice(ENTRY_ALPHABET) for _unused in range(n))

    return f"EL-{pick(4)}-{pick(4)}"


def normalize_entry_code(raw):
    """Accepte « el-7k4q-92md », « EL7K4Q92MD » ou avec des espaces ; renvoie la forme EL-XXXX-XXXX."""
    letters = "".join(c for c in (raw or "").upper() if c.isalnum())
    if letters.startswith("EL") and len(letters) == 10:
        return f"EL-{letters[2:6]}-{letters[6:10]}"
    return (raw or "").strip().upper()


class Table(models.Model):
    """Table de la salle : son numéro reste fixe (il est imprimé sur les billets), même si d'autres tables sont supprimées."""

    MAX_CAPACITY = 30

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="tables", verbose_name=_("événement"))
    number = models.PositiveIntegerField(_("numéro"))
    name = models.CharField(_("nom"), max_length=60, blank=True)
    capacity = models.PositiveSmallIntegerField(
        _("places"), default=12, validators=[MinValueValidator(1), MaxValueValidator(MAX_CAPACITY)],
    )

    class Meta:
        ordering = ["number"]
        constraints = [models.UniqueConstraint(fields=["event", "number"], name="unique_table_number_per_event")]
        verbose_name = _("table")
        verbose_name_plural = _("tables")

    def __str__(self):
        return self.label

    @property
    def label(self):
        """« Table 4 », ou « Table 4 · Famille de la mariée » quand la table porte un nom."""
        base = gettext("Table %(n)d") % {"n": self.number}
        return f"{base} · {self.name}" if self.name else base


class Guest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("En attente")
        CONFIRMED = "confirmed", _("Présent")
        DECLINED = "declined", _("Absent")
        MAYBE = "maybe", _("Peut-être")

    class Channel(models.TextChoices):
        EMAIL = "email", _("Email")
        WHATSAPP = "whatsapp", "WhatsApp"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="guests", verbose_name=_("événement"))
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="invitations", verbose_name=_("compte lié"),
    )
    name = models.CharField(_("nom"), max_length=150)
    email = models.EmailField(_("email"), blank=True)
    phone = models.CharField(_("téléphone"), max_length=30, blank=True)
    status = models.CharField(_("statut"), max_length=10, choices=Status.choices, default=Status.PENDING)
    companions = models.PositiveIntegerField(_("accompagnants"), default=0)
    sent_via = models.CharField(_("canal d'envoi"), max_length=10, choices=Channel.choices, default=Channel.WHATSAPP)
    language = models.CharField(_("langue de l'invitation"), max_length=5, choices=settings.LANGUAGES, default=settings.LANGUAGE_CODE)
    magic_token = models.UUIDField(_("lien magique"), default=uuid.uuid4, unique=True, editable=False)
    invitation_sent_at = models.DateTimeField(_("invitation envoyée le"), null=True, blank=True)
    replied_at = models.DateTimeField(_("répondu le"), null=True, blank=True)
    wants_gift = models.BooleanField(_("souhaite offrir un cadeau"), null=True, blank=True)
    entry_code = models.CharField(_("code d'entrée"), max_length=14, unique=True, editable=False)
    checked_in_at = models.DateTimeField(_("arrivé le"), null=True, blank=True)
    thanks_sent_at = models.DateTimeField(_("remerciement envoyé le"), null=True, blank=True)
    added_on_site = models.BooleanField(_("ajouté sur place"), default=False)
    table = models.ForeignKey(
        Table, on_delete=models.SET_NULL, null=True, blank=True, related_name="guests", verbose_name=_("table"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("invité")
        verbose_name_plural = _("invités")

    def __str__(self):
        return f"{self.name} ({self.event})"

    def save(self, *args, **kwargs):
        if not self.entry_code:
            code = new_entry_code()
            while Guest.objects.filter(entry_code=code).exists():
                code = new_entry_code()
            self.entry_code = code
        if self.table_id and (self.status != self.Status.CONFIRMED or self.table.event_id != self.event_id):
            # Seuls les invités présents ont une place, à une table de leur événement : sinon la place se libère
            self.table = None
            if kwargs.get("update_fields") is not None and "table" not in kwargs["update_fields"]:
                kwargs["update_fields"] = [*kwargs["update_fields"], "table"]
        super().save(*args, **kwargs)

    def get_invitation_url(self):
        return reverse("events:invitation", args=[self.magic_token])

    def get_ticket_url(self):
        return reverse("events:invitation_ticket", args=[self.magic_token])

    @property
    def party_size(self):
        """Nombre de personnes qui entrent avec ce billet : l'invité et ses accompagnants."""
        return 1 + self.companions

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


class Reminder(models.Model):
    """Une relance envoyée à un invité qui n'a pas encore répondu (journal : quand, par quel canal, par qui)."""

    guest = models.ForeignKey(Guest, on_delete=models.CASCADE, related_name="reminders", verbose_name=_("invité"))
    channel = models.CharField(_("canal"), max_length=10, choices=Guest.Channel.choices)
    automatic = models.BooleanField(_("automatique"), default=False)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    sent_at = models.DateTimeField(_("envoyée le"), default=timezone.now)

    class Meta:
        ordering = ["-sent_at", "-pk"]
        verbose_name = _("relance")
        verbose_name_plural = _("relances")

    def __str__(self):
        return f"{self.guest.name} : {self.sent_at:%d/%m/%Y}"


def album_path(instance, filename):
    """Nom de fichier tiré au hasard : l'adresse d'une photo ne se devine pas."""
    return f"albums/{instance.event_id}/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}"


class AlbumPhoto(models.Model):
    """Photo de l'album partagé de l'événement : ajoutée par l'équipe ou par un invité présent."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="photos", verbose_name=_("événement"))
    guest = models.ForeignKey(
        Guest, on_delete=models.SET_NULL, null=True, blank=True, related_name="album_photos", verbose_name=_("ajoutée par"),
    )
    image = models.ImageField(_("photo"), upload_to=album_path)
    thumb = models.ImageField(_("miniature"), upload_to=album_path)
    created_at = models.DateTimeField(_("ajoutée le"), auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = _("photo de l'album")
        verbose_name_plural = _("photos de l'album")

    def __str__(self):
        return f"{self.event} : photo {self.pk}"


@receiver(post_delete, sender=AlbumPhoto)
def delete_album_files(sender, instance, **kwargs):
    """Une photo supprimée (ou son événement) ne laisse pas de fichier derrière elle."""
    for field in (instance.image, instance.thumb):
        if field:
            field.delete(save=False)


class CheckIn(models.Model):
    """Journal du pointage à l'entrée : chaque lecture de QR code ou pointage manuel, accepté ou refusé."""

    class Result(models.TextChoices):
        VALIDATED = "validated", _("Entrée validée")
        DUPLICATE = "duplicate", _("QR déjà utilisé")
        UNKNOWN = "unknown", _("QR inconnu")
        WRONG_EVENT = "wrong_event", _("Autre événement")
        WALK_IN = "walk_in", _("Ajouté sur place")
        CANCELLED = "cancelled", _("Pointage annulé")

    class Source(models.TextChoices):
        QR = "qr", _("QR code")
        MANUAL = "manual", _("Recherche")
        WALK_IN = "walk_in", _("Sur place")

    REFUSED = (Result.DUPLICATE, Result.UNKNOWN, Result.WRONG_EVENT)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="check_ins", verbose_name=_("événement"))
    guest = models.ForeignKey(Guest, on_delete=models.SET_NULL, null=True, blank=True, related_name="check_ins", verbose_name=_("invité"))
    code = models.CharField(_("code lu"), max_length=60, blank=True)
    result = models.CharField(_("résultat"), max_length=12, choices=Result.choices)
    source = models.CharField(_("origine"), max_length=10, choices=Source.choices, default=Source.QR)
    scanned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("pointage")
        verbose_name_plural = _("pointages")

    def __str__(self):
        return f"{self.event} : {self.get_result_display()}"

    @property
    def is_refused(self):
        return self.result in self.REFUSED


class EventEvaluation(models.Model):
    """Evaluation post-evenement soumise par un organisateur invite."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="evaluations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="evaluations")
    stars = models.PositiveIntegerField(_("note"), validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(_("commentaire"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "user")
        verbose_name = _("évaluation")
        verbose_name_plural = _("évaluations")

    def __str__(self):
        return f"{self.event} - {self.stars}/5"
