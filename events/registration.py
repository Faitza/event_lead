"""Inscription gratuite à un événement public sans billet payant (décision du 20 octobre 2026).

La personne clique sur « Je participe » : elle est ajoutée à la liste des invités, présence confirmée,
et reçoit le même billet d'entrée avec QR code qu'un invité. Les places sont limitées au nombre maximum
d'invités de l'événement ; la vérification se fait sous verrou pour que deux personnes ne prennent pas
la dernière place en même temps.
"""
from django.db import transaction
from django.utils import timezone

from .models import Event, Guest


class FullError(Exception):
    pass


def is_open(event):
    return (event.is_public and event.status == Event.Status.ACTIVE and not event.is_past
            and not (event.price_htg and event.price_htg > 0))


def places_left(event):
    return max(event.max_guests - event.guests.count(), 0)


def register(event, user):
    """Inscrit `user` et renvoie son invitation. Déjà inscrit : renvoie l'inscription existante."""
    with transaction.atomic():
        event = Event.objects.select_for_update().get(pk=event.pk)
        guest = event.guests.filter(user=user).first()
        if guest is not None:
            return guest
        if places_left(event) <= 0:
            raise FullError
        return Guest.objects.create(
            event=event, user=user, name=user.display_name, email=user.email, phone=user.phone,
            sent_via=Guest.Channel.EMAIL, language=user.language or Guest._meta.get_field("language").default,
            status=Guest.Status.CONFIRMED, replied_at=timezone.now(), from_ticket=True,
        )
