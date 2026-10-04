"""Anti double paiement (point 10 de docs/solidite.md).

Le formulaire de paiement porte un numéro unique (champ caché `idem`), nouveau à chaque affichage. Le paiement
est d'abord enregistré « en attente » avec ce numéro (contrainte d'unicité en base), puis seulement débité.
Un deuxième envoi du même formulaire, même au même instant, ne peut donc pas créer un deuxième débit :
il retrouve le premier paiement.
"""
import logging
import re

from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _

from .gateways import charge
from .models import Payment

logger = logging.getLogger("eventlead.payments")

KEY_RE = re.compile(r"^[0-9a-f]{32}$")


def key_from(request):
    key = (request.POST.get("idem") or "").strip().lower()
    return key if KEY_RE.match(key) else None


def existing(key):
    return Payment.objects.filter(idempotency_key=key).first() if key else None


def reserve(key, **fields):
    """Crée le paiement « en attente ». Renvoie (paiement, créé) : créé=False si ce formulaire a déjà été envoyé."""
    try:
        with transaction.atomic():
            return Payment.objects.create(idempotency_key=key, status=Payment.Status.PENDING, **fields), True
    except IntegrityError:
        if key is None:
            raise
        return Payment.objects.get(idempotency_key=key), False


def safe_charge(method, cleaned, amount):
    """Appelle le service de paiement. S'il plante ou ne répond pas, le paiement est refusé proprement (point 08)."""
    try:
        return charge(method, cleaned, amount)
    except Exception:
        logger.exception("Service de paiement %s en échec", method)
        return Payment.Status.FAILED, _("Le service de paiement ne répond pas. Aucun montant n'a été débité. Réessayez dans quelques minutes.")


def duplicate_message(payment):
    if payment.status == Payment.Status.SUCCESS:
        return _("Ce paiement a déjà été effectué (référence %(reference)s) : rien n'a été débité une deuxième fois.") % {"reference": payment.reference}
    if payment.status == Payment.Status.PENDING:
        return _("Ce paiement est déjà en cours de traitement (référence %(reference)s). Patientez quelques secondes puis rechargez la page.") % {"reference": payment.reference}
    return _("Ce paiement a été refusé (référence %(reference)s). Vérifiez vos informations puis réessayez.") % {"reference": payment.reference}
