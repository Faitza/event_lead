"""Tableau de bord administrateur : CRUD événements et invités, suivi, exports."""
import csv
from urllib.parse import quote

from django.contrib import messages
from django.db.models import Count, Max, Min, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import admin_required
from gifts.models import GiftClaim

from .forms import EventForm, EventGroupForm, GuestForm
from .geocoding import geocode_address
from .models import Event, EventGroup, Guest

# ---------------------------------------------------------------------------
# Événements
# ---------------------------------------------------------------------------


@admin_required
def event_list(request):
    events = Event.objects.select_related("group").annotate(
        num_guests=Count("guests", distinct=True),
        num_confirmed=Count("guests", filter=Q(guests__status=Guest.Status.CONFIRMED), distinct=True),
        num_gifts=Count("gifts", distinct=True),
    ).order_by("-date")
    q = request.GET.get("q", "").strip()
    etype = request.GET.get("type", "")
    if q:
        events = events.filter(Q(title__icontains=q) | Q(venue__icontains=q))
    if etype in dict(Event.EventType.choices):
        events = events.filter(event_type=etype)
    return render(request, "dashboard/events/list.html", {"events": events, "q": q, "etype": etype})


# ---------------------------------------------------------------------------
# Groupes d'événements
# ---------------------------------------------------------------------------


@admin_required
def group_list(request):
    groups = EventGroup.objects.annotate(
        num_events=Count("events", distinct=True),
        num_public=Count("events", filter=Q(events__event_type=Event.EventType.PUBLIC), distinct=True),
        first_date=Min("events__date"),
        last_date=Max("events__date"),
    )
    return render(request, "dashboard/groups/list.html", {"groups": groups})


def _group_form_page(request, group=None):
    form = EventGroupForm(request.POST or None, request.FILES or None, instance=group)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Groupe créé." if group is None else "Groupe mis à jour.")
        return redirect("dashboard:group_list")
    return render(request, "dashboard/groups/form.html", {"form": form, "group": group, "is_new": group is None})


@admin_required
def group_create(request):
    return _group_form_page(request)


@admin_required
def group_edit(request, pk):
    return _group_form_page(request, get_object_or_404(EventGroup, pk=pk))


@admin_required
def group_delete(request, pk):
    group = get_object_or_404(EventGroup, pk=pk)
    if request.method == "POST":
        group.delete()
        messages.success(request, "Groupe supprimé. Ses événements sont conservés.")
        return redirect("dashboard:group_list")
    count = group.events.count()
    return render(request, "dashboard/confirm_delete.html", {
        "object": group, "kind": "le groupe", "blocked": False,
        "note": f"Les {count} événement{'s' if count > 1 else ''} du groupe ne sont pas supprimés : "
                "ils redeviennent des événements indépendants." if count else "",
        "cancel_url": reverse("dashboard:group_list"),
    })


def _save_event(request, form):
    event = form.save(commit=False)
    if not event.created_by_id:
        event.created_by = request.user
    venue_changed = "venue" in form.changed_data
    if event.venue and (not event.has_location or (venue_changed and not {"latitude", "longitude"} & set(form.changed_data))):
        coords = geocode_address(event.venue)
        if coords:
            event.latitude, event.longitude = coords
        else:
            messages.warning(request, "Adresse non localisée automatiquement. Placez le repère sur la carte si besoin.")
    event.save()
    return event


@admin_required
def event_create(request):
    form = EventForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        event = _save_event(request, form)
        messages.success(request, "Événement créé. Ajoutez maintenant vos invités et votre liste de cadeaux.")
        return redirect("dashboard:event_detail", pk=event.pk)
    return render(request, "dashboard/events/form.html", {"form": form, "is_new": True})


@admin_required
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    form = EventForm(request.POST or None, request.FILES or None, instance=event)
    if request.method == "POST" and form.is_valid():
        _save_event(request, form)
        messages.success(request, "Événement mis à jour.")
        return redirect("dashboard:event_detail", pk=event.pk)
    return render(request, "dashboard/events/form.html", {"form": form, "event": event, "is_new": False})


@admin_required
def event_delete(request, pk):
    event = get_object_or_404(Event, pk=pk)
    has_claims = GiftClaim.objects.filter(gift__event=event).exists()
    if request.method == "POST":
        if has_claims:
            messages.error(request, "Impossible de supprimer : des invités ont déjà choisi des cadeaux. Annulez plutôt l'événement.")
            return redirect("dashboard:event_detail", pk=pk)
        event.delete()
        messages.success(request, "Événement supprimé.")
        return redirect("dashboard:event_list")
    return render(request, "dashboard/confirm_delete.html", {
        "object": event, "kind": "l'événement", "blocked": has_claims,
        "cancel_url": reverse("dashboard:event_detail", args=[pk]),
    })


def _tracking_context(event):
    gifts = event.gifts.annotate(num_claims=Count("claims")).prefetch_related("claims__guest")
    return {
        "event": event,
        "stats": event.stats(),
        "gifts": gifts,
        "recent": event.guests.exclude(replied_at=None).order_by("-replied_at")[:8],
        "now": timezone.now(),
    }


@admin_required
def event_detail(request, pk):
    """Suivi en temps réel des réponses (rafraîchi par fetch toutes les 5 s)."""
    event = get_object_or_404(Event, pk=pk)
    ctx = _tracking_context(event)
    ctx["guests"] = event.guests.all()
    ctx["evaluations"] = event.evaluations.select_related("user")
    return render(request, "dashboard/events/detail.html", ctx)


@admin_required
@require_GET
def event_live(request, pk):
    event = get_object_or_404(Event, pk=pk)
    html = render_to_string("dashboard/events/_live.html", _tracking_context(event), request=request)
    return HttpResponse(html)


@admin_required
@require_GET
def geocode(request):
    coords = geocode_address(request.GET.get("q", "").strip())
    if not coords:
        return JsonResponse({"found": False}, status=404)
    return JsonResponse({"found": True, "lat": coords[0], "lng": coords[1]})


# ---------------------------------------------------------------------------
# Invités
# ---------------------------------------------------------------------------


def invitation_links(request, guest):
    url = request.build_absolute_uri(guest.get_invitation_url())
    event = guest.event
    text = (
        f"Bonjour {guest.name}, vous êtes invité(e) à « {event.title} » le "
        f"{event.date:%d/%m/%Y} à {event.time:%H:%M}. Merci de confirmer votre présence ici : {url}"
    )
    phone = "".join(c for c in guest.phone if c.isdigit())
    return {
        "url": url,
        "whatsapp": f"https://wa.me/{phone}?text={quote(text)}" if phone else f"https://wa.me/?text={quote(text)}",
        "mailto": f"mailto:{guest.email}?subject={quote('Invitation : ' + event.title)}&body={quote(text)}",
    }


@admin_required
def guest_list(request):
    guests = Guest.objects.select_related("event").annotate(num_gifts=Count("gift_claims"))
    events = Event.objects.order_by("-date")
    event_id = request.GET.get("event", "")
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()
    current_event = None
    if event_id.isdigit():
        current_event = events.filter(pk=event_id).first()
        guests = guests.filter(event_id=event_id)
    if status in dict(Guest.Status.choices):
        guests = guests.filter(status=status)
    if q:
        guests = guests.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q))
    for g in guests:
        g.links = invitation_links(request, g)
    return render(request, "dashboard/guests/list.html", {
        "guests": guests, "events": events, "current_event": current_event,
        "status": status, "q": q, "statuses": Guest.Status.choices,
        "export_qs": request.GET.urlencode(),
    })


@admin_required
def guest_create(request):
    initial = {}
    if request.GET.get("event", "").isdigit():
        initial["event"] = request.GET["event"]
    form = GuestForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        guest = form.save()
        messages.success(request, f"{guest.name} a été ajouté(e). Son lien d'invitation est prêt à être envoyé.")
        if "add_another" in request.POST:
            return redirect(f"{reverse('dashboard:guest_create')}?event={guest.event_id}")
        return redirect(f"{reverse('dashboard:guest_list')}?event={guest.event_id}")
    return render(request, "dashboard/guests/form.html", {"form": form, "is_new": True})


@admin_required
def guest_edit(request, pk):
    guest = get_object_or_404(Guest, pk=pk)
    form = GuestForm(request.POST or None, instance=guest)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Invité mis à jour.")
        return redirect(f"{reverse('dashboard:guest_list')}?event={guest.event_id}")
    return render(request, "dashboard/guests/form.html", {
        "form": form, "guest": guest, "is_new": False, "links": invitation_links(request, guest),
    })


@admin_required
def guest_delete(request, pk):
    guest = get_object_or_404(Guest, pk=pk)
    blocked = guest.gift_claims.exists()
    back = f"{reverse('dashboard:guest_list')}?event={guest.event_id}"
    if request.method == "POST":
        if blocked:
            messages.error(request, "Cet invité a choisi des cadeaux : sa réponse est définitive et ne peut pas être supprimée.")
        else:
            guest.delete()
            messages.success(request, "Invité supprimé.")
        return redirect(back)
    return render(request, "dashboard/confirm_delete.html", {
        "object": guest, "kind": "l'invité", "blocked": blocked, "cancel_url": back,
    })


@admin_required
@require_POST
def guest_mark_sent(request, pk):
    """V1 : l'admin envoie le lien manuellement (WhatsApp ou e-mail) puis le marque comme envoyé."""
    guest = get_object_or_404(Guest, pk=pk)
    guest.invitation_sent_at = timezone.now()
    guest.save(update_fields=["invitation_sent_at"])
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"ok": True, "sent_at": guest.invitation_sent_at.isoformat()})
    messages.success(request, f"Invitation de {guest.name} marquée comme envoyée.")
    return redirect(request.POST.get("next") or reverse("dashboard:guest_list"))


def _filtered_guests(request):
    guests = Guest.objects.select_related("event").prefetch_related("gift_claims__gift").order_by("event__date", "name")
    if request.GET.get("event", "").isdigit():
        guests = guests.filter(event_id=request.GET["event"])
    if request.GET.get("status") in dict(Guest.Status.choices):
        guests = guests.filter(status=request.GET["status"])
    return guests


@admin_required
def guest_export_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="invites-eventlead.csv"'
    response.write("﻿")  # BOM pour l'ouverture correcte dans Excel
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Événement", "Nom", "E-mail", "Téléphone", "Canal", "Statut", "Accompagnants",
                     "Cadeaux choisis", "Répondu le", "Lien d'invitation"])
    for g in _filtered_guests(request):
        writer.writerow([
            g.event.title, g.name, g.email, g.phone, g.get_sent_via_display(), g.get_status_display(),
            g.companions, ", ".join(c.gift.name for c in g.gift_claims.all()),
            timezone.localtime(g.replied_at).strftime("%d/%m/%Y %H:%M") if g.replied_at else "",
            request.build_absolute_uri(g.get_invitation_url()),
        ])
    return response


@admin_required
def guest_export_pdf(request):
    from xhtml2pdf import pisa

    guests = _filtered_guests(request)
    event = None
    if request.GET.get("event", "").isdigit():
        event = Event.objects.filter(pk=request.GET["event"]).first()
    html = render_to_string("dashboard/guests/export_pdf.html", {
        "guests": guests, "event": event, "generated_at": timezone.localtime(),
    })
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="invites-eventlead.pdf"'
    result = pisa.CreatePDF(html, dest=response, encoding="utf-8")
    if result.err:
        return HttpResponse("Erreur lors de la génération du PDF.", status=500)
    return response
