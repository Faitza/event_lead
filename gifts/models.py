from django.db import models
from django.utils.translation import gettext_lazy as _

from events.models import Event, Guest

GIFT_ICONS = [
    ("bi-gift", _("Cadeau")),
    ("bi-cup-hot", _("Service à thé / café")),
    ("bi-cup-straw", _("Verres")),
    ("bi-egg-fried", _("Cuisine")),
    ("bi-house-heart", _("Maison")),
    ("bi-lamp", _("Lampe")),
    ("bi-tv", _("Télévision")),
    ("bi-speaker", _("Enceinte")),
    ("bi-camera", _("Appareil photo")),
    ("bi-laptop", _("Ordinateur")),
    ("bi-phone", _("Telephone")),
    ("bi-headphones", _("Casque audio")),
    ("bi-basket", _("Panier")),
    ("bi-flower1", _("Fleurs")),
    ("bi-airplane", _("Voyage")),
    ("bi-suitcase", _("Bagages")),
    ("bi-bicycle", _("Vélo")),
    ("bi-book", _("Livre")),
    ("bi-palette", _("Décoration")),
    ("bi-wallet2", _("Enveloppe")),
    ("bi-gem", _("Bijou")),
    ("bi-watch", _("Montre")),
    ("bi-music-note-beamed", _("Musique")),
    ("bi-heart", _("Coup de cœur")),
]


class Gift(models.Model):
    """Cadeau de la liste d'un evenement.

    Pas de description ni de prix : l'invite et l'hote reglent ces details
    entre eux, hors plateforme. Les reservations passent par GiftClaim pour
    gerer proprement quantity > 1.
    """

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="gifts", verbose_name=_("événement"))
    name = models.CharField(_("nom du cadeau"), max_length=150)
    icon_name = models.CharField(_("icône"), max_length=50, choices=GIFT_ICONS, default="bi-gift")
    quantity = models.PositiveIntegerField(_("quantité"), default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("cadeau")
        verbose_name_plural = _("cadeaux")

    def __str__(self):
        return self.name

    @property
    def claimed_count(self):
        # Utilise l'annotation si elle est presente (evite une requete par cadeau)
        annotated = getattr(self, "num_claims", None)
        return annotated if annotated is not None else self.claims.count()

    @property
    def remaining(self):
        return max(self.quantity - self.claimed_count, 0)

    @property
    def is_available(self):
        return self.remaining > 0

    @property
    def can_be_deleted(self):
        return not self.claims.exists()


class GiftClaim(models.Model):
    """Reservation definitive d'un cadeau par un invite (jamais supprimable cote invite)."""

    gift = models.ForeignKey(Gift, on_delete=models.PROTECT, related_name="claims", verbose_name=_("cadeau"))
    guest = models.ForeignKey(Guest, on_delete=models.PROTECT, related_name="gift_claims", verbose_name=_("invité"))
    claimed_at = models.DateTimeField(_("choisi le"), auto_now_add=True)

    class Meta:
        unique_together = ("gift", "guest")
        ordering = ["claimed_at"]
        verbose_name = _("cadeau choisi")
        verbose_name_plural = _("cadeaux choisis")

    def __str__(self):
        return f"{self.gift} - {self.guest.name}"
