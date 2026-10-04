"""Flux invité multi-étapes accessible par lien magique (section 6)."""
from urllib.parse import quote

from django.contrib import messages
from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext
from django.views.decorators.http import require_GET

from ads.models import Ad
from gifts.models import GiftClaim
from payments.models import Contribution
from gifts.services import (
    GiftUnavailableError,
    ResponseLockedError,
    confirm_response,
    gift_state,
    gifts_for_guest,
)

from . import checkin, thanks
from .forms import GiftSelectionForm, GiftWishForm, PresenceForm
from .messaging import supported_language
from .models import Event, Guest, normalize_entry_code
from .qr import entry_url, qr_png, qr_svg


def _session_key(guest):
    return f"invitation_{guest.magic_token}"


def _get_state(request, guest):
    return request.session.get(_session_key(guest), {})


def _set_state(request, guest, **values):
    state = _get_state(request, guest)
    state.update(values)
    request.session[_session_key(guest)] = state
    return state


# Étapes du parcours : identifiant interne -> libellé affiché (traduit) dans la barre de progression.
STEP_LABELS = {
    "presence": gettext_lazy("Présence"),
    "gifts": gettext_lazy("Cadeaux"),
    "selection": gettext_lazy("Sélection"),
    "recap": gettext_lazy("Récapitulatif"),
    "confirmation": gettext_lazy("Confirmation"),
}


def _steps(event):
    if event.gifts.exists():
        return ["presence", "gifts", "selection", "recap", "confirmation"]
    if event.accept_contributions:
        return ["presence", "gifts", "recap", "confirmation"]  # sans liste de cadeaux : seulement la contribution en argent
    return ["presence", "recap", "confirmation"]


def _ctx(guest, step_name, **extra):
    steps = _steps(guest.event)
    index = steps.index(step_name) + 1 if step_name in steps else len(steps)
    labels = [STEP_LABELS[s] for s in steps]
    return {"guest": guest, "event": guest.event, "steps": labels, "step_index": index, "step_total": len(steps), **extra}


def _load_guest(token):
    return get_object_or_404(Guest.objects.select_related("event"), magic_token=token)


def _guard(request, guest):
    """Renvoie une réponse si l'invitation n'est plus modifiable, sinon None."""
    event = guest.event
    if guest.is_locked:
        claims = GiftClaim.objects.filter(guest=guest).select_related("gift")
        contribution = Contribution.objects.filter(guest=guest).first()
        return render(request, "invitation/already_answered.html", _ctx(
            guest, "confirmation", claims=claims, contribution=contribution, thanks_ready=thanks.can_view(guest),
        ))
    if event.status != Event.Status.ACTIVE or event.is_past:
        return render(request, "invitation/closed.html", _ctx(guest, "presence"))
    return None


def invitation_presence(request, token):
    """Étape 1 : présence (Oui / Non / Peut-être), accompagnants et carte du lieu."""
    guest = _load_guest(token)
    blocked = _guard(request, guest)
    if blocked:
        return blocked
    event = guest.event
    state = _get_state(request, guest)
    initial = {"status": state.get("status"), "companions": state.get("companions", 0)}
    form = PresenceForm(request.POST or None, event=event, initial=initial)
    if request.method == "POST" and form.is_valid():
        status = form.cleaned_data["status"]
        _set_state(request, guest, status=status, companions=form.cleaned_data["companions"])
        if status == Guest.Status.CONFIRMED and event.has_gift_step:
            return redirect("events:invitation_gift_question", token=token)
        _set_state(request, guest, wants_gift=None, gift_ids=[])
        return redirect("events:invitation_recap", token=token)
    return render(request, "invitation/step_presence.html", _ctx(guest, "presence", form=form))


def invitation_gift_question(request, token):
    """Étape 2 : « Souhaitez-vous envoyer un cadeau ? » (seulement si Oui + cadeaux existants)."""
    guest = _load_guest(token)
    blocked = _guard(request, guest)
    if blocked:
        return blocked
    state = _get_state(request, guest)
    if state.get("status") != Guest.Status.CONFIRMED or not guest.event.has_gift_step:
        return redirect("events:invitation", token=token)
    has_gifts = guest.event.gifts.exists()
    form = GiftWishForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        wants = form.cleaned_data["wants_gift"] and has_gifts
        _set_state(request, guest, wants_gift=wants)
        if wants:
            return redirect("events:invitation_gift_list", token=token)
        _set_state(request, guest, gift_ids=[])
        return redirect("events:invitation_recap", token=token)
    return render(request, "invitation/step_gift_question.html", _ctx(
        guest, "gifts", form=form, state=state, has_gifts=has_gifts, can_contribute=guest.event.accept_contributions,
    ))


def invitation_gift_list(request, token):
    """Étape 3 : cases à cocher avec états disponible / sélectionné / complet."""
    guest = _load_guest(token)
    blocked = _guard(request, guest)
    if blocked:
        return blocked
    state = _get_state(request, guest)
    if state.get("status") != Guest.Status.CONFIRMED or not state.get("wants_gift"):
        return redirect("events:invitation", token=token)
    gifts = list(gifts_for_guest(guest.event, guest))
    available_ids = [g.pk for g in gifts if g.is_available]
    form = GiftSelectionForm(request.POST or None, available_ids=available_ids)
    if request.method == "POST":
        if form.is_valid():
            _set_state(request, guest, gift_ids=form.cleaned_data["gifts"])
            return redirect("events:invitation_recap", token=token)
        messages.error(request, _("Un cadeau sélectionné n'est plus disponible. La liste a été actualisée."))
    selected = set(state.get("gift_ids", []))
    for gift in gifts:
        gift.state = gift_state(gift, selected)
    return render(request, "invitation/step_gift_list.html", _ctx(guest, "selection", form=form, gifts=gifts))


@require_GET
def invitation_gift_availability(request, token):
    """Rafraîchissement AJAX (polling toutes les 5 s) de la disponibilité des cadeaux."""
    guest = _load_guest(token)
    data = [
        {
            "id": g.pk, "remaining": g.remaining, "available": g.is_available, "mine": bool(g.mine),
            # Libellé déjà traduit et accordé : la page l'affiche tel quel
            "label": ngettext("%(n)d disponible", "%(n)d disponibles", g.remaining) % {"n": g.remaining},
        }
        for g in gifts_for_guest(guest.event, guest)
    ]
    return JsonResponse({"gifts": data})


def invitation_recap(request, token):
    """Étape 4 : récapitulatif + « Confirmer définitivement » (écriture atomique)."""
    guest = _load_guest(token)
    blocked = _guard(request, guest)
    if blocked:
        return blocked
    state = _get_state(request, guest)
    if not state.get("status"):
        return redirect("events:invitation", token=token)
    selected_ids = state.get("gift_ids", []) if state.get("wants_gift") else []
    selected_gifts = list(guest.event.gifts.filter(pk__in=selected_ids))

    if request.method == "POST":
        try:
            confirm_response(
                guest.pk,
                status=state["status"],
                companions=state.get("companions", 0),
                wants_gift=state.get("wants_gift"),
                gift_ids=selected_ids,
            )
        except GiftUnavailableError as exc:
            remaining = [i for i in selected_ids if i not in {g.pk for g in exc.gifts}]
            _set_state(request, guest, gift_ids=remaining)
            messages.error(
                request,
                ngettext(
                    "Désolé, ce cadeau vient d'être choisi par un autre invité : %(cadeaux)s. Merci de revoir votre sélection.",
                    "Désolé, ces cadeaux viennent d'être choisis par d'autres invités : %(cadeaux)s. Merci de revoir votre sélection.",
                    len(exc.gifts),
                ) % {"cadeaux": ", ".join(g.name for g in exc.gifts)},
            )
            return redirect("events:invitation_gift_list", token=token)
        except ResponseLockedError:
            return redirect("events:invitation", token=token)
        request.session.pop(_session_key(guest), None)
        request.session[f"invitation_done_{token}"] = True
        return redirect("events:invitation_done", token=token)

    return render(
        request,
        "invitation/step_recap.html",
        _ctx(guest, "recap", state=state, selected_gifts=selected_gifts,
             status_label=dict(Guest.Status.choices).get(state["status"])),
    )


def _ad_sequence():
    return list(Ad.objects.filter(is_active=True, show_after_reply=True).values_list("pk", flat=True))


def _after_ads_url():
    """Fin du parcours : la page d'accueil, au défilé des publications et des événements publics."""
    return reverse("core:landing") + "#affiche"


def invitation_done(request, token):
    """Étape 5 : « c'est confirmé » (avec le QR code d'entrée), puis une publication et l'accueil."""
    guest = _load_guest(token)
    if guest.replied_at is None:
        return redirect("events:invitation", token=token)
    ads = _ad_sequence()
    next_url = reverse("events:invitation_ad", args=[token, ads[0]]) if ads else _after_ads_url()
    claims = GiftClaim.objects.filter(guest=guest).select_related("gift")
    contribution = Contribution.objects.filter(guest=guest).first()
    # Un invité présent a le temps de toucher « Voir mon QR code d'entrée » avant la redirection
    delay = 8 if guest.status == Guest.Status.CONFIRMED else 3
    return render(request, "invitation/step_done.html", _ctx(
        guest, "confirmation", next_url=next_url, claims=claims, delay=delay, ads_follow=bool(ads), contribution=contribution,
    ))


def invitation_ad(request, token, ad_id):
    """Page publicité affichée après la réponse (section 7), puis retour à l'accueil."""
    guest = _load_guest(token)
    ad = get_object_or_404(Ad, pk=ad_id, is_active=True)
    Ad.objects.filter(pk=ad.pk).update(views=F("views") + 1)
    ads = _ad_sequence()
    try:
        position = ads.index(ad.pk)
    except ValueError:
        position = len(ads) - 1
    following = ads[position + 1] if position + 1 < len(ads) else None
    next_url = reverse("events:invitation_ad", args=[token, following]) if following else _after_ads_url()
    return render(request, "ads/ad_page.html", {
        "ad": ad, "guest": guest, "next_url": next_url,
        "position": position + 1, "total": len(ads),
    })


# ---------------------------------------------------------------------------
# QR code d'entrée
# ---------------------------------------------------------------------------


def _ticket_guest(token):
    """Le billet d'entrée n'existe que pour un invité qui a confirmé sa présence."""
    guest = _load_guest(token)
    return guest if guest.status == Guest.Status.CONFIRMED and guest.replied_at else None


def invitation_ticket(request, token):
    guest = _ticket_guest(token)
    if guest is None:
        return redirect("events:invitation", token=token)
    link = request.build_absolute_uri(guest.get_ticket_url()) + f"?lang={supported_language(guest.language)}"
    share = _("Mon billet d'entrée pour « %(title)s » : %(url)s") % {"title": guest.event.title, "url": link}
    qr = qr_svg(entry_url(request, guest), label=_("QR code d'entrée de %(name)s") % {"name": guest.name})
    return render(request, "invitation/ticket.html", {
        "guest": guest, "event": guest.event, "qr": qr, "party": checkin.party_text(guest),
        "whatsapp_url": f"https://wa.me/?text={quote(share)}",
    })


@require_GET
def invitation_ticket_png(request, token):
    guest = _ticket_guest(token)
    if guest is None:
        return redirect("events:invitation", token=token)
    response = HttpResponse(qr_png(entry_url(request, guest)), content_type="image/png")
    response["Content-Disposition"] = f'attachment; filename="billet-{guest.entry_code}.png"'
    return response


def entry_code(request, code):
    """Adresse contenue dans le QR code. Public : rien sur l'invité. Équipe EventLead : validation de l'entrée."""
    code = normalize_entry_code(code)
    guest = Guest.objects.select_related("event").filter(entry_code=code).first()
    user = request.user
    staff = user.is_authenticated and user.is_admin_role
    result = None
    if staff and guest is not None and request.method == "POST":
        result = checkin.describe(checkin.scan(guest.event, code, user))
    return render(request, "invitation/entry_code.html", {
        "guest": guest if staff else None, "code": code, "staff": staff, "known": guest is not None, "result": result,
        "event": guest.event if guest and staff else None,
    })
