"""Contribution en argent d'un invité, à la place d'un cadeau (MonCash ou NatCash)."""
import re
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _

from events.models import Guest
from gifts.services import ResponseLockedError, confirm_response

from . import idempotency
from .models import Contribution, Payment

PRESET_AMOUNTS = (1000, 2500, 5000, 10000, 25000)
DEFAULT_AMOUNT = 5000
MIN_AMOUNT = 500
MAX_AMOUNT = 500000
METHODS = (Payment.Method.MONCASH, Payment.Method.NATCASH)


class ContributionError(Exception):
    """Une donnée refusée : le message est écrit pour l'invité."""


def parse_amount(raw):
    """Montant entier en HTG : accepte « 5000 », « 5 000 » ou « 5.000 »."""
    digits = re.sub(r"[\s  .,]", "", str(raw or ""))
    if not digits.isdigit():
        raise ContributionError(_("Indiquez un montant en gourdes."))
    amount = int(digits)
    if amount < MIN_AMOUNT:
        raise ContributionError(_("Le montant minimum est de %(min)s HTG.") % {"min": f"{MIN_AMOUNT:,}".replace(",", " ")})
    if amount > MAX_AMOUNT:
        raise ContributionError(_("Le montant maximum est de %(max)s HTG.") % {"max": f"{MAX_AMOUNT:,}".replace(",", " ")})
    return Decimal(amount)


def usd(amount):
    return (Decimal(amount) * settings.HTG_TO_USD_RATE).quantize(Decimal("0.01"))


def clean_message(raw):
    return " ".join(str(raw or "").split())[: Contribution.MESSAGE_MAX]


def contribute(guest, *, companions, amount, method, cleaned, message, key=None):
    """Encaisse la contribution puis confirme la réponse de l'invité (présent, sans cadeau), en une seule étape.

    Renvoie (paiement, texte). Si le paiement est refusé, aucune contribution n'est créée et la réponse de l'invité
    reste ouverte. Lève ResponseLockedError si l'invité a déjà répondu définitivement (rien n'est alors débité),
    ou si ce même formulaire (`key`) a déjà été envoyé : un double clic ne débite jamais deux fois.
    """
    if method not in METHODS:
        raise ContributionError(_("Choisissez MonCash ou NatCash."))
    with transaction.atomic():
        locked = Guest.objects.select_for_update().select_related("event").get(pk=guest.pk)
        if locked.is_locked or idempotency.existing(key):
            raise ResponseLockedError()
        payment, created = idempotency.reserve(
            key, kind=Payment.Kind.CONTRIBUTION, event=locked.event, guest=locked, user=None, method=method,
            amount_htg=amount, reference=Payment.generate_reference(method),
            payer_detail=cleaned.get("payer_detail", "")[:120],
        )
        if not created:
            raise ResponseLockedError()
        status, text = idempotency.safe_charge(method, cleaned, amount)
        payment.status = status
        payment.save(update_fields=["status"])
        if status != Payment.Status.SUCCESS:
            return payment, text
        Contribution.objects.create(
            event=locked.event, guest=locked, payment=payment, amount_htg=amount, message=clean_message(message),
        )
        confirm_response(locked.pk, status=Guest.Status.CONFIRMED, companions=companions, wants_gift=False, gift_ids=[])
    return payment, text
