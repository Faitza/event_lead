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


class Attribution(models.Model):
    """Provenance d'une inscription, d'un paiement, d'une demande d'aide ou d'un message (liens avec utm_*).

    Rien n'est envoyé à un service extérieur : les paramètres utm_* lus à l'arrivée sont gardés dans la session
    du visiteur (core/utm.py), puis recopiés ici quand il fait une de ces actions.
    """

    class Kind(models.TextChoices):
        SIGNUP = "signup", _("Inscription")
        PAYMENT = "payment", _("Paiement")
        HELP = "help", _("Demande d'aide")
        CONTACT = "contact", _("Message de contact")

    kind = models.CharField(_("action"), max_length=20, choices=Kind.choices)
    label = models.CharField(_("détail"), max_length=200, blank=True)
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="+", verbose_name=_("compte"))
    source = models.CharField("utm_source", max_length=120, blank=True)
    medium = models.CharField("utm_medium", max_length=120, blank=True)
    campaign = models.CharField("utm_campaign", max_length=120, blank=True)
    term = models.CharField("utm_term", max_length=120, blank=True)
    content = models.CharField("utm_content", max_length=120, blank=True)
    landing_page = models.CharField(_("page d'arrivée"), max_length=300, blank=True)
    created_at = models.DateTimeField(_("date"), auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"], name="attribution_created_idx"),
                   models.Index(fields=["source", "campaign"], name="attribution_source_idx")]
        verbose_name = _("provenance")
        verbose_name_plural = _("provenances")

    def __str__(self):
        return f"{self.get_kind_display()} - {self.source or '?'} / {self.campaign or '?'}"


class LogoVariant(models.Model):
    """Version du logo affichée sur tout le site pendant une période (Noël, Saint-Valentin, fête du drapeau...).

    Hors de ces périodes, le site montre le logo original. Chaque couleur existe en deux fichiers : un pour les
    fonds clairs, un pour les fonds sombres (pied de page, mode sombre). Fichiers prêts dans static/img/logo/.
    """

    class Preset(models.TextChoices):
        ORIGINAL = "original", _("Violet (original)")
        GOLD = "or", _("Or")
        PINK = "rose", _("Rose")
        RED = "rouge", _("Rouge")
        BLUE = "bleu", _("Bleu")
        GREEN = "vert", _("Vert")
        CUSTOM = "perso", _("Mon propre fichier")

    name = models.CharField(_("nom"), max_length=80, help_text=_("Par exemple : Noël 2026, Saint-Valentin."))
    preset = models.CharField(_("couleur"), max_length=12, choices=Preset.choices, default=Preset.GOLD)
    image = models.ImageField(_("logo pour fond clair"), upload_to="logos/", blank=True,
                              help_text=_("Seulement pour « Mon propre fichier » : PNG à fond transparent."))
    image_dark = models.ImageField(_("logo pour fond sombre"), upload_to="logos/", blank=True,
                                   help_text=_("Facultatif : sinon le logo pour fond clair est utilisé partout."))
    start_date = models.DateField(_("du"))
    end_date = models.DateField(_("au"))
    is_active = models.BooleanField(_("activé"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "-pk"]
        verbose_name = _("version du logo")
        verbose_name_plural = _("versions du logo")

    def __str__(self):
        return self.name

    @classmethod
    def current(cls, day=None):
        from django.utils import timezone
        day = day or timezone.localdate()
        return cls.objects.filter(is_active=True, start_date__lte=day, end_date__gte=day).first()

    @property
    def urls(self):
        """(fond clair, fond sombre) : adresses des deux fichiers à afficher."""
        from django.templatetags.static import static
        if self.preset == self.Preset.CUSTOM and self.image:
            light = self.image.url
            return light, (self.image_dark.url if self.image_dark else light)
        preset = self.preset if self.preset != self.Preset.CUSTOM else self.Preset.ORIGINAL
        return static(f"img/logo/eventlead-{preset}.png"), static(f"img/logo/eventlead-{preset}-sombre.png")

    def state(self, day=None):
        from django.utils import timezone
        day = day or timezone.localdate()
        if not self.is_active:
            return "off", _("Désactivé")
        if day < self.start_date:
            return "soon", _("À venir")
        if day > self.end_date:
            return "past", _("Terminé")
        return "live", _("En ce moment")
