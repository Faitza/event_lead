"""Remerciements et album photo (tableau de bord administrateur)."""
from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required

from . import album, reminders, thanks
from .messaging import thanks_links
from .models import AlbumPhoto, Event, Guest


def _stats(event):
    guests = event.guests.filter(status=Guest.Status.CONFIRMED)
    photos = event.photos.all()
    return {
        "published": thanks.is_published(event),
        "photos": photos.count(),
        "photos_by_guests": photos.filter(guest__isnull=False).count(),
        "present": guests.count(),
        "sent": guests.filter(thanks_sent_at__isnull=False).count(),
    }


@admin_required
def thanks_index(request):
    """Choix de l'événement : ceux qui ont des invités présents ou des photos, passés d'abord."""
    today = timezone.localdate()
    events = Event.objects.annotate(
        present=Count("guests", filter=Q(guests__status=Guest.Status.CONFIRMED), distinct=True),
        photo_count=Count("photos", distinct=True),
    ).filter(Q(present__gt=0) | Q(photo_count__gt=0))
    cards = [{"event": e, "stats": _stats(e)} for e in events]
    past = sorted((c for c in cards if c["event"].date <= today), key=lambda c: (c["event"].date, c["event"].time), reverse=True)
    upcoming = sorted((c for c in cards if c["event"].date > today), key=lambda c: (c["event"].date, c["event"].time))
    return render(request, "dashboard/thanks/index.html", {"past": past, "upcoming": upcoming})


@admin_required
def thanks_event(request, pk):
    event = get_object_or_404(Event, pk=pk)
    rows = []
    for guest in thanks.present_guests(event).select_related("event"):
        links = thanks_links(request, guest)
        rows.append({"guest": guest, "channel": reminders.effective_channel(guest), "links": links})
    stats = _stats(event)
    # Exemple du message envoyé, dans la langue de la personne connectée, avec un lien factice
    sample = Guest(event=event, name="Marie-Claude", language=translation.get_language() or settings.LANGUAGE_CODE)
    preview = thanks_links(request, sample)
    return render(request, "dashboard/thanks/event.html", {
        "event": event, "rows": rows, "stats": stats, "photos": event.photos.select_related("guest"),
        "message": event.thanks_message, "default_message": thanks.default_message(), "message_max": thanks.MESSAGE_MAX,
        "preview_body": preview["body"].replace(preview["url"], _("[lien personnel de l'invité]")),
        "preview_subject": preview["subject"], "email_demo": reminders.email_demo_mode(),
        "max_per_upload": album.MAX_PER_UPLOAD, "max_per_event": album.MAX_PER_EVENT,
        "to_email": sum(1 for r in rows if r["channel"] == "email" and not r["guest"].thanks_sent_at),
        "to_whatsapp": sum(1 for r in rows if r["channel"] == "whatsapp" and not r["guest"].thanks_sent_at),
    })


def _back(event):
    return redirect("dashboard:thanks_event", pk=event.pk)


@admin_required
@require_POST
def thanks_message(request, pk):
    event = get_object_or_404(Event, pk=pk)
    event.thanks_message = thanks.clean_message(request.POST.get("message"))
    event.save(update_fields=["thanks_message"])
    messages.success(request, _("Message de remerciement enregistré."))
    return _back(event)


@admin_required
@require_POST
def thanks_publish(request, pk):
    """Publier rend la page « Merci » et l'album visibles pour les invités présents ; dépublier les referme."""
    event = get_object_or_404(Event, pk=pk)
    if request.POST.get("action") == "unpublish":
        thanks.unpublish(event)
        messages.success(request, _("Les remerciements ne sont plus visibles par les invités."))
    else:
        thanks.publish(event)
        messages.success(request, _("Les remerciements et l'album sont publiés : les invités présents peuvent les ouvrir avec leur lien."))
    return _back(event)


@admin_required
@require_POST
def thanks_upload(request, pk):
    event = get_object_or_404(Event, pk=pk)
    added, errors = album.add_photos(event, request.FILES.getlist("photos"))
    if added:
        messages.success(request, ngettext("%(n)d photo ajoutée à l'album.", "%(n)d photos ajoutées à l'album.", added) % {"n": added})
    for error in errors:
        messages.error(request, error)
    return _back(event)


@admin_required
@require_POST
def thanks_photo_delete(request, pk, photo_pk):
    event = get_object_or_404(Event, pk=pk)
    photo = get_object_or_404(AlbumPhoto, pk=photo_pk, event=event)
    photo.delete()
    messages.success(request, _("Photo supprimée de l'album."))
    return _back(event)


@admin_required
@require_POST
def thanks_send_one(request, pk, guest_pk):
    """E-mail : le serveur l'envoie. WhatsApp : la page ouvre WhatsApp, puis enregistre l'envoi ici."""
    event = get_object_or_404(Event, pk=pk)
    guest = get_object_or_404(Guest, pk=guest_pk, event=event)
    try:
        channel = thanks.send_thanks(event, guest, request)
    except thanks.ThanksError as error:
        return JsonResponse({"ok": False, "error": str(error), "name": guest.name}, status=400)
    return JsonResponse({"ok": True, "channel": channel, "name": guest.name})


@admin_required
@require_POST
def thanks_send_all(request, pk):
    """« Envoyer par e-mail » : tous les e-mails partent ; les WhatsApp restent à envoyer depuis le téléphone."""
    event = get_object_or_404(Event, pk=pk)
    result = thanks.send_all_emails(event, request)
    parts = []
    if result["sent"]:
        parts.append(ngettext("%(n)d e-mail de remerciement envoyé.", "%(n)d e-mails de remerciement envoyés.", result["sent"]) % {"n": result["sent"]})
    if result["whatsapp_waiting"]:
        parts.append(ngettext(
            "%(n)d remerciement WhatsApp reste à envoyer : cliquez sur « WhatsApp » sur sa ligne.",
            "%(n)d remerciements WhatsApp restent à envoyer : cliquez sur « WhatsApp » sur chaque ligne.", result["whatsapp_waiting"],
        ) % {"n": result["whatsapp_waiting"]})
    if result["failed"]:
        parts.append(ngettext("%(n)d e-mail n'a pas pu partir.", "%(n)d e-mails n'ont pas pu partir.", result["failed"]) % {"n": result["failed"]})
    if not parts:
        parts.append(_("Aucun remerciement à envoyer pour le moment."))
    (messages.warning if result["failed"] else messages.success)(request, " ".join(parts))
    return _back(event)
