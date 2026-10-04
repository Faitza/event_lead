"""Remerciements et album partagé, côté invité (lien personnel, sans connexion)."""
from django.contrib import messages
from django.http import FileResponse
from django.shortcuts import redirect, render
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_GET

from . import album, thanks
from .models import AlbumPhoto
from .views_invitation import _load_guest


PREVIEW_COUNT = 6  # photos montrées d'abord ; la dernière porte « +N » et ouvre le reste


def _closed(token):
    return redirect("events:invitation", token=token)


def invitation_thanks(request, token):
    """Page « Merci » : message des hôtes, album, ajout de photos, merci personnel pour les cadeaux."""
    guest = _load_guest(token)
    if not thanks.can_view(guest):
        return _closed(token)
    event = guest.event
    if request.method == "POST":
        if int(request.META.get("CONTENT_LENGTH") or 0) > album.MAX_REQUEST_BYTES:
            messages.error(request, _("Envoi trop lourd : ajoutez vos photos en plusieurs fois."))
        else:
            added, errors = album.add_photos(event, request.FILES.getlist("photos"), guest)
            if added:
                messages.success(request, ngettext("%(n)d photo ajoutée. Merci !", "%(n)d photos ajoutées. Merci !", added) % {"n": added})
            for error in errors:
                messages.error(request, error)
        return redirect("events:invitation_thanks", token=token)
    photos = list(event.photos.all())
    mine = sum(1 for p in photos if p.guest_id == guest.pk)
    return render(request, "invitation/step_thanks.html", {
        "guest": guest, "event": event, "photos": photos, "photo_count": len(photos),
        "message": thanks.message_for(event), "personal_line": thanks.personal_line(guest),
        "can_add": len(photos) < album.MAX_PER_EVENT and mine < album.MAX_PER_GUEST,
        "preview_count": PREVIEW_COUNT, "extra_count": max(0, len(photos) - PREVIEW_COUNT),
    })


@require_GET
def invitation_album_zip(request, token):
    """Télécharger toutes les photos de l'album en un seul fichier .zip."""
    guest = _load_guest(token)
    if not thanks.can_view(guest):
        return _closed(token)
    event = guest.event
    if not AlbumPhoto.objects.filter(event=event).exists():
        messages.error(request, _("L'album est encore vide."))
        return redirect("events:invitation_thanks", token=token)
    name = f"album-{slugify(event.title) or 'evenement'}.zip"
    return FileResponse(album.build_zip(event), as_attachment=True, filename=name, content_type="application/zip")
