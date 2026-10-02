from django.db import models

from events.models import Event, Guest

GIFT_ICONS = [
    ("bi-gift", "Cadeau"),
    ("bi-cup-hot", "Service à thé / café"),
    ("bi-cup-straw", "Verres"),
    ("bi-egg-fried", "Cuisine"),
    ("bi-house-heart", "Maison"),
    ("bi-lamp", "Lampe"),
    ("bi-tv", "Télévision"),
    ("bi-speaker", "Enceinte"),
    ("bi-camera", "Appareil photo"),
    ("bi-laptop", "Ordinateur"),
    ("bi-phone", "Telephone"),
    ("bi-headphones", "Casque audio"),
    ("bi-basket", "Panier"),
    ("bi-flower1", "Fleurs"),
    ("bi-airplane", "Voyage"),
    ("bi-suitcase", "Bagages"),
    ("bi-bicycle", "Vélo"),
    ("bi-book", "Livre"),
    ("bi-palette", "Décoration"),
    ("bi-wallet2", "Enveloppe"),
    ("bi-gem", "Bijou"),
    ("bi-watch", "Montre"),
    ("bi-music-note-beamed", "Musique"),
    ("bi-heart", "Coup de cœur"),
]


class Gift(models.Model):
    """Cadeau de la liste d'un evenement.

    Pas de description ni de prix : l'invite et l'hote reglent ces details
    entre eux, hors plateforme. Les reservations passent par GiftClaim pour
    gerer proprement quantity > 1.
    """

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="gifts", verbose_name="événement")
    name = models.CharField("nom du cadeau", max_length=150)
    icon_name = models.CharField("icône", max_length=50, choices=GIFT_ICONS, default="bi-gift")
    quantity = models.PositiveIntegerField("quantité", default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "cadeau"
        verbose_name_plural = "cadeaux"

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

    gift = models.ForeignKey(Gift, on_delete=models.PROTECT, related_name="claims", verbose_name="cadeau")
    guest = models.ForeignKey(Guest, on_delete=models.PROTECT, related_name="gift_claims", verbose_name="invité")
    claimed_at = models.DateTimeField("choisi le", auto_now_add=True)

    class Meta:
        unique_together = ("gift", "guest")
        ordering = ["claimed_at"]
        verbose_name = "cadeau choisi"
        verbose_name_plural = "cadeaux choisis"

    def __str__(self):
        return f"{self.gift} - {self.guest.name}"
