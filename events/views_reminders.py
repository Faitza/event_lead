"""Relances des invités sans réponse (tableau de bord administrateur)."""
from datetime import time

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import admin_required

from . import reminders
from .messaging import reminder_links
from .models import Event, Guest


@admin_required
def reminder_index(request):
    """Choix de l'événement : ceux qui ont des invités sans réponse, à venir d'abord."""
    today = timezone.localdate()
    cards = []
    for event in Event.objects.filter(guests__isnull=False).distinct():
        rows = reminders.overview(event)
        stat = reminders.stats(event, rows)
        cards.append({"event": event, "stats": stat, "open": reminders.event_accepts_reminders(event)})
    upcoming = sorted((c for c in cards if c["event"].date >= today), key=lambda c: (c["event"].date, c["event"].time))
    past = sorted((c for c in cards if c["event"].date < today), key=lambda c: (c["event"].date, c["event"].time), reverse=True)
    return render(request, "dashboard/reminders/index.html", {"upcoming": upcoming, "past": past})


def _table_context(event):
    rows = reminders.overview(event)
    stat = reminders.stats(event, rows)
    top = max(reminders.limit_for(event), max((r.count for r in rows), default=0))
    return {
        "event": event,
        "rows": rows,
        "stats": stat,
        "levels": [
            {"n": n, "count": stat["once"] if n == 1 else stat["twice"] if n == 2 else stat["thrice"]}
            for n in range(1, min(top, 3) + 1)
        ],
        "limit": reminders.limit_for(event),
        "accepts": reminders.event_accepts_reminders(event),
        "reminder_time": reminders.reminder_time(event),
        "today": timezone.localdate(),
        "email_demo": reminders.email_demo_mode(),
    }


def _with_links(request, context):
    for row in context["rows"]:
        row.links = reminder_links(request, row.guest)
    return context


@admin_required
def reminder_event(request, pk):
    event = get_object_or_404(Event, pk=pk)
    context = _with_links(request, _table_context(event))
    # Exemple de message dans la langue de la personne connectée, avec un lien factice à la place du lien personnel
    sample = Guest(event=event, name="Marie-Claude", language=translation.get_language() or settings.LANGUAGE_CODE)
    preview = reminder_links(request, sample)
    context.update({
        "preview_body": preview["body"].replace(preview["url"], _("[lien personnel de l'invité]")),
        "preview_subject": preview["subject"],
        "first_choices": reminders.FIRST_AFTER_CHOICES,
        "every_choices": reminders.EVERY_CHOICES,
        "max_choices": reminders.MAX_CHOICES,
        "hour_choices": [(h, time(h)) for h in reminders.HOUR_CHOICES],
    })
    return render(request, "dashboard/reminders/event.html", context)


@admin_required
@require_GET
def reminder_live(request, pk):
    event = get_object_or_404(Event, pk=pk)
    context = _with_links(request, _table_context(event))
    return HttpResponse(render_to_string("dashboard/reminders/_live.html", context, request=request))


@admin_required
@require_POST
def reminder_settings(request, pk):
    event = get_object_or_404(Event, pk=pk)
    values, error = reminders.validate_settings(request.POST)
    if error:
        messages.error(request, error)
    else:
        for field, value in values.items():
            setattr(event, field, value)
        event.save(update_fields=list(values))
        messages.success(request, _("Réglages des relances enregistrés."))
    return redirect("dashboard:reminder_event", pk=event.pk)


@admin_required
@require_POST
def reminder_send_one(request, pk, guest_pk):
    """E-mail : le serveur l'envoie. WhatsApp : la page ouvre WhatsApp, puis enregistre la relance ici."""
    event = get_object_or_404(Event, pk=pk)
    guest = get_object_or_404(Guest, pk=guest_pk, event=event)
    try:
        channel = reminders.remind_guest(event, guest, request.user, request)
    except reminders.ReminderError as error:
        return JsonResponse({"ok": False, "error": str(error), "name": guest.name}, status=400)
    return JsonResponse({"ok": True, "channel": channel, "name": guest.name})


@admin_required
@require_POST
def reminder_send_due(request, pk):
    """« Envoyer maintenant » : tous les e-mails à échéance partent ; les WhatsApp restent à envoyer depuis le téléphone."""
    event = get_object_or_404(Event, pk=pk)
    result = reminders.send_due_emails(event, request.user, request)
    sent, failed, waiting = result[reminders.SENT], result[reminders.FAILED], result["whatsapp_waiting"]
    parts = []
    if sent:
        parts.append(ngettext("%(n)d e-mail de relance envoyé.", "%(n)d e-mails de relance envoyés.", sent) % {"n": sent})
    if waiting:
        parts.append(ngettext(
            "%(n)d relance WhatsApp reste à envoyer : cliquez sur « Relancer » sur sa ligne.",
            "%(n)d relances WhatsApp restent à envoyer : cliquez sur « Relancer » sur chaque ligne.", waiting,
        ) % {"n": waiting})
    if failed:
        parts.append(ngettext("%(n)d e-mail n'a pas pu partir.", "%(n)d e-mails n'ont pas pu partir.", failed) % {"n": failed})
    if not parts:
        parts.append(_("Aucune relance à envoyer pour le moment."))
    (messages.warning if failed else messages.success)(request, " ".join(parts))
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"ok": not failed, "sent": sent, "waiting": waiting, "failed": failed, "message": " ".join(parts)})
    return redirect(reverse("dashboard:reminder_event", args=[event.pk]))
