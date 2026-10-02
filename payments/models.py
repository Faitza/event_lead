import secrets

from django.conf import settings
from django.db import models

from events.models import Event, Guest

REF_PREFIX = {"moncash": "MC", "natcash": "NAT", "stripe": "ST", "paypal": "PP"}


class Payment(models.Model):
    class Method(models.TextChoices):
        MONCASH = "moncash", "MonCash"
        NATCASH = "natcash", "NatCash"
        STRIPE = "stripe", "Carte bancaire (Stripe)"
        PAYPAL = "paypal", "PayPal"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        SUCCESS = "success", "Réussi"
        FAILED = "failed", "Échoué"

    class Kind(models.TextChoices):
        TICKET = "ticket", "Billet"
        ORGANIZER_ACCESS = "organizer_access", "Accès Organisateur VIP"

    kind = models.CharField("type", max_length=20, choices=Kind.choices, default=Kind.TICKET)
    event = models.ForeignKey(
        Event, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments", verbose_name="événement"
    )
    guest = models.ForeignKey(
        Guest, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments", verbose_name="invité"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments",
        verbose_name="utilisateur",
    )
    method = models.CharField("mode de paiement", max_length=10, choices=Method.choices)
    amount_htg = models.DecimalField("montant (HTG)", max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField("nombre de billets", default=1)
    reference = models.CharField("référence", max_length=30, unique=True)
    status = models.CharField("statut", max_length=10, choices=Status.choices, default=Status.PENDING)
    payer_detail = models.CharField(
        "détail payeur", max_length=120, blank=True,
        help_text="Numéro masqué ou e-mail du payeur (jamais de données de carte complètes).",
    )
    created_at = models.DateTimeField("créé le", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "paiement"
        verbose_name_plural = "paiements"

    def __str__(self):
        return self.reference

    @classmethod
    def generate_reference(cls, method):
        prefix = REF_PREFIX.get(method, "EL")
        while True:
            ref = f"{prefix}-{secrets.token_hex(3).upper()}"
            if not cls.objects.filter(reference=ref).exists():
                return ref

    @property
    def amount_usd(self):
        return (self.amount_htg * settings.HTG_TO_USD_RATE).quantize(self.amount_htg.__class__("0.01"))
