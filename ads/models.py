from django.db import models
from django.utils.translation import gettext_lazy as _


class Ad(models.Model):
    title = models.CharField(_("titre"), max_length=150)
    icon_name = models.CharField(_("icône"), max_length=50, default="bi-megaphone")
    message = models.TextField(_("message"))
    image = models.ImageField(_("image"), upload_to="ads/", null=True, blank=True)
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

    class Meta:
        ordering = ["order", "-created_at"]
        verbose_name = _("publicité")
        verbose_name_plural = _("publicités")

    def __str__(self):
        return self.title

    @property
    def ctr(self):
        """Taux de clic en pourcentage."""
        return round(self.clicks * 100 / self.views, 1) if self.views else 0.0

    @property
    def image_url(self):
        return self.image.url if self.image else ""
