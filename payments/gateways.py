"""Passerelles de paiement.

V1 : simulation (PAYMENT_DEMO_MODE=True). Aucune API réelle n'est appelée.
V2 : brancher ici les vraies API (stripe.PaymentIntent, MonCash REST, PayPal
Orders) en lisant les clés depuis settings (variables d'environnement).
"""
from django.conf import settings
from django.utils.translation import gettext as _

from .models import Payment

DECLINED_TEST_CARD = "4000000000000002"


def charge(method, cleaned_data, amount_htg):
    """Retourne (statut, message)."""
    if not settings.PAYMENT_DEMO_MODE:  # pragma: no cover - V2
        raise NotImplementedError("Intégration réelle des paiements prévue en V2.")
    if method == Payment.Method.MONCASH and cleaned_data.get("otp") != settings.MONCASH_DEMO_OTP:
        return Payment.Status.FAILED, _("Code OTP MonCash incorrect. Le paiement a été refusé.")
    if method == Payment.Method.STRIPE and cleaned_data.get("card_digits") == DECLINED_TEST_CARD:
        return Payment.Status.FAILED, _("Carte refusée par la banque émettrice.")
    return Payment.Status.SUCCESS, _("Paiement accepté.")
