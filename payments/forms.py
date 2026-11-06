import re
from datetime import date

from django import forms
from django.utils.translation import gettext as _

from .models import Payment

PHONE_RE = re.compile(r"^(\+?509)?\s?[2-5]\d{3}\s?-?\d{4}$")


def luhn_ok(number):
    digits = [int(d) for d in number][::-1]
    total = 0
    for i, d in enumerate(digits):
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class PaymentForm(forms.Form):
    """Formulaire unique validé selon le mode de paiement choisi.

    Les données de carte ne sont jamais stockées : seuls les 4 derniers
    chiffres sont conservés dans Payment.payer_detail.
    """

    method = forms.ChoiceField(choices=Payment.Method.choices, widget=forms.HiddenInput)
    quantity = forms.IntegerField(min_value=1, max_value=20, initial=1, required=False)
    # MonCash / NatCash
    phone = forms.CharField(required=False, max_length=20)
    otp = forms.CharField(required=False, max_length=6)
    pin = forms.CharField(required=False, max_length=4)
    # Stripe
    card_number = forms.CharField(required=False, max_length=23)
    card_expiry = forms.CharField(required=False, max_length=5)
    card_cvc = forms.CharField(required=False, max_length=4)
    card_name = forms.CharField(required=False, max_length=100)
    # PayPal
    paypal_email = forms.EmailField(required=False)
    paypal_password = forms.CharField(required=False, widget=forms.PasswordInput)

    def _require(self, *names):
        for name in names:
            if not self.cleaned_data.get(name):
                self.add_error(name, _("Champ obligatoire."))

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("method")
        cleaned["quantity"] = cleaned.get("quantity") or 1
        if method in (Payment.Method.MONCASH, Payment.Method.NATCASH):
            phone = (cleaned.get("phone") or "").strip()
            if not PHONE_RE.match(phone):
                self.add_error("phone", _("Numéro haïtien invalide (8 chiffres, ex : 3712 3456)."))
            if method == Payment.Method.MONCASH and not re.fullmatch(r"\d{6}", cleaned.get("otp") or ""):
                self.add_error("otp", _("Le code OTP contient 6 chiffres."))
            if method == Payment.Method.NATCASH and not re.fullmatch(r"\d{4}", cleaned.get("pin") or ""):
                self.add_error("pin", _("Le code PIN contient 4 chiffres."))
            digits = re.sub(r"\D", "", phone)[-8:]
            cleaned["payer_detail"] = f"+509 **** {digits[-4:]}" if digits else ""
        elif method == Payment.Method.STRIPE:
            self._require("card_number", "card_expiry", "card_cvc", "card_name")
            number = re.sub(r"\D", "", cleaned.get("card_number") or "")
            if number and (len(number) < 13 or not luhn_ok(number)):
                self.add_error("card_number", _("Numéro de carte invalide."))
            exp = cleaned.get("card_expiry") or ""
            m = re.fullmatch(r"(\d{2})/(\d{2})", exp)
            if exp and not m:
                self.add_error("card_expiry", _("Format MM/AA."))
            elif m:
                month, year = int(m.group(1)), 2000 + int(m.group(2))
                today = date.today()
                if not 1 <= month <= 12 or (year, month) < (today.year, today.month):
                    self.add_error("card_expiry", _("Carte expirée ou date invalide."))
            cvc = cleaned.get("card_cvc") or ""
            if cvc and not re.fullmatch(r"\d{3,4}", cvc):
                self.add_error("card_cvc", _("CVC invalide."))
            cleaned["card_digits"] = number
            cleaned["payer_detail"] = f"Carte **** {number[-4:]}" if number else ""
        elif method == Payment.Method.PAYPAL:
            self._require("paypal_email", "paypal_password")
            cleaned["payer_detail"] = cleaned.get("paypal_email") or ""
        return cleaned
