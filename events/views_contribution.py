"""Page « Contribuer en argent » du flux invité (lien magique, sans connexion)."""
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from core.ratelimit import ratelimit
from gifts.services import ResponseLockedError
from payments import contributions
from payments import idempotency
from payments.forms import PaymentForm
from payments.models import Payment

from .models import Guest
from .views_invitation import _ctx, _get_state, _guard, _load_guest, _session_key


@ratelimit("payment", 10, 600)
def invitation_contribution(request, token):
    """À la place d'un cadeau : montant, MonCash ou NatCash, petit mot ; le paiement confirme la réponse."""
    guest = _load_guest(token)
    blocked = _guard(request, guest)
    if blocked:
        return blocked
    event = guest.event
    state = _get_state(request, guest)
    if not event.accept_contributions or state.get("status") != Guest.Status.CONFIRMED:
        return redirect("events:invitation", token=token)

    amount = contributions.DEFAULT_AMOUNT
    method = Payment.Method.MONCASH
    message = ""
    form = PaymentForm(request.POST or None)
    form.fields["method"].choices = [(m, m) for m in contributions.METHODS]
    if request.method == "POST":
        message = contributions.clean_message(request.POST.get("message"))
        method = request.POST.get("method", method)
        try:
            amount_value = contributions.parse_amount(request.POST.get("amount"))
            amount = int(amount_value)
        except contributions.ContributionError as error:
            amount_value = None
            messages.error(request, str(error))
        if amount_value is not None and form.is_valid():
            try:
                payment, text = contributions.contribute(
                    guest, companions=state.get("companions", 0), amount=amount_value, method=form.cleaned_data["method"],
                    cleaned=form.cleaned_data, message=message, key=idempotency.key_from(request),
                )
            except ResponseLockedError:
                return redirect("events:invitation", token=token)
            if payment.status == Payment.Status.SUCCESS:
                request.session.pop(_session_key(guest), None)
                request.session[f"invitation_done_{token}"] = True
                return redirect("events:invitation_done", token=token)
            # Paiement refusé : la fenêtre se rouvre sur le même mode avec le motif, la réponse reste ouverte
            form.add_error(None, _("%(message)s Référence : %(reference)s.") % {"message": text, "reference": payment.reference})

    return render(request, "invitation/step_contribution.html", _ctx(
        guest, "selection" if event.gifts.exists() else "gifts", form=form, state=state, amount=amount, amount_usd=contributions.usd(amount), method=method,
        message=message, presets=contributions.PRESET_AMOUNTS, min_amount=contributions.MIN_AMOUNT,
        max_amount=contributions.MAX_AMOUNT, message_max=contributions.Contribution.MESSAGE_MAX,
        pay_methods=[str(m) for m in contributions.METHODS], contribution=True,
        has_gifts=event.gifts.exists(), rate=str(settings.HTG_TO_USD_RATE),
    ))
