import re
from urllib.parse import parse_qs, quote, urlparse

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtube-nocookie.com"}
FACEBOOK_HOSTS = {"facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com", "fb.watch"}
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


def youtube_id(url):
    """Identifiant d'une vidéo YouTube (watch?v=, youtu.be/, shorts/, embed/), ou "" si le lien n'en est pas une."""
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        return ""
    parts = [p for p in parsed.path.split("/") if p]
    if host == "youtu.be":
        candidate = parts[0] if parts else ""
    elif parts and parts[0] in {"shorts", "embed", "live", "v"}:
        candidate = parts[1] if len(parts) > 1 else ""
    else:
        candidate = (parse_qs(parsed.query).get("v") or [""])[0]
    return candidate if YOUTUBE_ID.match(candidate) else ""


def is_facebook_video(url):
    return (urlparse(url or "").hostname or "").lower() in FACEBOOK_HOSTS


class AdQuerySet(models.QuerySet):
    def live(self):
        """Publicités visibles sur le site : actives, payées par l'annonceur et dans leur période de diffusion."""
        today = timezone.localdate()
        return self.filter(is_active=True, is_paid=True).filter(
            Q(start_date__isnull=True) | Q(start_date__lte=today),
            Q(end_date__isnull=True) | Q(end_date__gte=today),
        )


class Ad(models.Model):
    """Publicité d'un partenaire qui paie pour être affiché (image ou vidéo)."""

    advertiser = models.CharField(_("annonceur"), max_length=150, blank=True,
                                  help_text=_("Le partenaire ou la personne qui paie cette publicité."))
    advertiser_phone = models.CharField(_("téléphone ou WhatsApp de l'annonceur"), max_length=30, blank=True)
    is_paid = models.BooleanField(_("payée"), default=False,
                                  help_text=_("La publicité n'apparaît sur le site qu'une fois cochée « payée »."))
    amount_htg = models.DecimalField(_("montant payé (HTG)"), max_digits=10, decimal_places=2, null=True, blank=True)
    start_date = models.DateField(_("début de diffusion"), null=True, blank=True)
    end_date = models.DateField(_("fin de diffusion"), null=True, blank=True,
                                help_text=_("Après cette date, la publicité ne s'affiche plus. Vide : sans fin."))
    title = models.CharField(_("titre"), max_length=150)
    icon_name = models.CharField(_("icône"), max_length=50, default="bi-megaphone")
    message = models.TextField(_("message"))
    image = models.ImageField(_("image"), upload_to="ads/", null=True, blank=True)
    video = models.FileField(
        _("vidéo"), upload_to="ads/videos/", null=True, blank=True,
        help_text=_("Jouée sans le son, en boucle. L'image ci-dessus s'affiche avant qu'elle démarre."),
    )
    video_url = models.URLField(
        _("lien d'une vidéo YouTube ou Facebook"), blank=True,
        help_text=_("Utilisé seulement s'il n'y a pas de fichier vidéo."),
    )
    sponsor_link = models.URLField(_("lien du sponsor"))
    skip_after_seconds = models.PositiveIntegerField(_("passer après (secondes)"), default=5)
    views = models.PositiveIntegerField(_("vues"), default=0)
    clicks = models.PositiveIntegerField(_("clics"), default=0)
    is_active = models.BooleanField(_("active"), default=True)
    show_after_reply = models.BooleanField(
        _("afficher après la réponse d'un invité"), default=True,
        help_text=_("Si coché, la publicité fait partie de la séquence affichée après une réponse."),
    )
    order = models.PositiveIntegerField(_("ordre d'affichage"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AdQuerySet.as_manager()

    class Meta:
        ordering = ["order", "-created_at"]
        indexes = [models.Index(fields=["is_active", "order"], name="ad_active_order_idx")]
        verbose_name = _("publicité")
        verbose_name_plural = _("publicités")

    def __str__(self):
        return self.title

    @property
    def state(self):
        """(code, libellé) de diffusion, pour le tableau de bord."""
        today = timezone.localdate()
        if not self.is_paid:
            return "unpaid", _("En attente de paiement")
        if not self.is_active:
            return "off", _("Désactivée")
        if self.start_date and self.start_date > today:
            return "soon", _("Commence le %(date)s") % {"date": self.start_date.strftime("%d/%m/%Y")}
        if self.end_date and self.end_date < today:
            return "ended", _("Terminée")
        return "live", _("En ligne")

    @property
    def ctr(self):
        """Taux de clic en pourcentage."""
        return round(self.clicks * 100 / self.views, 1) if self.views else 0.0

    @property
    def image_url(self):
        return self.image.url if self.image else ""

    @property
    def video_embed_url(self):
        """Adresse du lecteur YouTube ou Facebook, sans le son et en boucle ; "" s'il y a un fichier vidéo ou aucun lien."""
        if self.video or not self.video_url:
            return ""
        vid = youtube_id(self.video_url)
        if vid:
            return (f"https://www.youtube-nocookie.com/embed/{vid}?autoplay=1&mute=1&loop=1&playlist={vid}"
                    "&playsinline=1&rel=0&modestbranding=1&enablejsapi=1")
        if is_facebook_video(self.video_url):
            return ("https://www.facebook.com/plugins/video.php?href=" + quote(self.video_url, safe="")
                    + "&autoplay=true&mute=true&show_text=false")
        return ""

    @property
    def has_video(self):
        return bool(self.video) or bool(self.video_embed_url)
