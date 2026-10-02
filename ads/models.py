from django.db import models


class Ad(models.Model):
    title = models.CharField("titre", max_length=150)
    icon_name = models.CharField("icône", max_length=50, default="bi-megaphone")
    message = models.TextField("message")
    image = models.ImageField("image", upload_to="ads/", null=True, blank=True)
    sponsor_link = models.URLField("lien du sponsor")
    skip_after_seconds = models.PositiveIntegerField("passer après (secondes)", default=5)
    views = models.PositiveIntegerField("vues", default=0)
    clicks = models.PositiveIntegerField("clics", default=0)
    is_active = models.BooleanField("active", default=True)
    show_after_reply = models.BooleanField(
        "afficher après la réponse d'un invité", default=True,
        help_text="Si coché, la publicité fait partie de la séquence affichée après une réponse.",
    )
    order = models.PositiveIntegerField("ordre d'affichage", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "-created_at"]
        verbose_name = "publicité"
        verbose_name_plural = "publicités"

    def __str__(self):
        return self.title

    @property
    def ctr(self):
        """Taux de clic en pourcentage."""
        return round(self.clicks * 100 / self.views, 1) if self.views else 0.0

    @property
    def image_url(self):
        return self.image.url if self.image else ""
