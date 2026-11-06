"""Gestion de la liste de cadeaux par l'administrateur (seul à voir les donateurs)."""
import csv

from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from accounts.decorators import admin_required
from events.models import Event

from .forms import GiftForm
from .models import Gift


def _back(event_id):
    return f"{reverse('dashboard:gift_list')}?event={event_id}"


@admin_required
def gift_list(request):
    events = Event.objects.annotate(num_gifts=Count("gifts")).order_by("-date")
    event_id = request.GET.get("event", "")
    current = events.filter(pk=event_id).first() if event_id.isdigit() else events.filter(num_gifts__gt=0).first()
    gifts = []
    if current:
        gifts = current.gifts.annotate(num_claims=Count("claims")).prefetch_related("claims__guest")
    totals = {
        "count": len(gifts),
        "units": sum(g.quantity for g in gifts),
        "taken": sum(g.num_claims for g in gifts),
    }
    return render(request, "dashboard/gifts/list.html", {
        "events": events, "current": current, "gifts": gifts, "totals": totals,
    })


@admin_required
def gift_create(request):
    initial = {"icon_name": "bi-gift", "quantity": 1}
    if request.GET.get("event", "").isdigit():
        initial["event"] = request.GET["event"]
    form = GiftForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        gift = form.save()
        messages.success(request, _("« %(name)s » ajouté à la liste.") % {"name": gift.name})
        if "add_another" in request.POST:
            return redirect(f"{reverse('dashboard:gift_create')}?event={gift.event_id}")
        return redirect(_back(gift.event_id))
    return render(request, "dashboard/gifts/form.html", {"form": form, "is_new": True})


@admin_required
def gift_edit(request, pk):
    with transaction.atomic():
        gift = get_object_or_404(Gift.objects.select_for_update(), pk=pk)
        form = GiftForm(request.POST or None, instance=gift)
        if request.method == "POST" and form.is_valid():
            form.save()
            messages.success(request, _("Cadeau mis à jour."))
            return redirect(_back(gift.event_id))
    return render(request, "dashboard/gifts/form.html", {"form": form, "gift": gift, "is_new": False})


@admin_required
def gift_delete(request, pk):
    gift = get_object_or_404(Gift, pk=pk)
    if request.method == "POST":
        with transaction.atomic():
            gift = Gift.objects.select_for_update().get(pk=pk)
            if gift.claims.exists():
                messages.error(request, _("Ce cadeau a déjà été choisi par un invité : il ne peut pas être supprimé."))
            else:
                gift.delete()
                messages.success(request, _("Cadeau supprimé."))
        return redirect(_back(gift.event_id))
    return render(request, "dashboard/confirm_delete.html", {
        "object": gift, "kind": _("le cadeau"), "blocked": not gift.can_be_deleted, "cancel_url": _back(gift.event_id),
    })


@admin_required
def gift_export_csv(request):
    gifts = Gift.objects.select_related("event").prefetch_related("claims__guest").order_by("event__date", "name")
    if request.GET.get("event", "").isdigit():
        gifts = gifts.filter(event_id=request.GET["event"])
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="%s.csv"' % _("cadeaux-eventlead")
    response.write("﻿")
    writer = csv.writer(response, delimiter=";")
    writer.writerow([_("Événement"), _("Cadeau"), _("Quantité"), _("Choisis"), _("Restants"), _("Statut"), _("Donateur(s)"), _("Choisi le")])
    for gift in gifts:
        claims = list(gift.claims.all())
        remaining = max(gift.quantity - len(claims), 0)
        writer.writerow([
            gift.event.title, gift.name, gift.quantity, len(claims), remaining,
            _("Complet") if remaining == 0 else _("Disponible"),
            ", ".join(c.guest.name for c in claims),
            ", ".join(timezone.localtime(c.claimed_at).strftime("%d/%m/%Y %H:%M") for c in claims),
        ])
    return response
