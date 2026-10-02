"""Logique métier du module cadeaux (section 5 du cahier des charges).

Toute écriture sur Gift/GiftClaim passe par ici, dans une transaction atomique
avec verrouillage des lignes (select_for_update) pour empêcher deux invités de
prendre simultanément la dernière unité d'un même cadeau.
"""
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef
from django.utils import timezone

from events.models import Guest

from .models import Gift, GiftClaim


class GiftUnavailableError(Exception):
    """Un ou plusieurs cadeaux ne sont plus disponibles au moment de la confirmation."""

    def __init__(self, gifts):
        self.gifts = gifts
        names = ", ".join(g.name for g in gifts)
        super().__init__(f"Déjà pris entre-temps : {names}")


class ResponseLockedError(Exception):
    """L'invité a déjà confirmé définitivement sa réponse."""


def gifts_for_guest(event, guest):
    """Cadeaux annotés pour l'affichage invité : restant + déjà choisi par cet invité.

    L'invité ne voit jamais QUI a pris un cadeau, seulement s'il est encore disponible.
    """
    return (
        event.gifts.annotate(
            num_claims=Count("claims"),
            mine=Exists(GiftClaim.objects.filter(gift=OuterRef("pk"), guest=guest)),
        )
        .order_by("name")
    )


def gift_state(gift, selected_ids=()):
    if getattr(gift, "mine", False):
        return "mine"
    if gift.pk in selected_ids and gift.is_available:
        return "selected"
    return "available" if gift.is_available else "taken"


@transaction.atomic
def confirm_response(guest_id, status, companions, wants_gift, gift_ids):
    """Écrit définitivement la réponse de l'invité.

    - verrouille l'invité et chacun des cadeaux demandés (ordre stable = pas d'interblocage) ;
    - vérifie la disponibilité réelle (quantity - claims) sous verrou ;
    - crée les GiftClaim puis met à jour l'invité.
    Lève GiftUnavailableError si un cadeau a été pris entre-temps : toute la
    transaction est annulée, rien n'est écrit.
    """
    guest = Guest.objects.select_for_update().select_related("event").get(pk=guest_id)
    if guest.is_locked:
        raise ResponseLockedError()

    gift_ids = sorted(set(gift_ids or [])) if status == Guest.Status.CONFIRMED and wants_gift else []
    unavailable = []
    locked_gifts = []
    for gift_id in gift_ids:
        gift = Gift.objects.select_for_update().get(pk=gift_id, event=guest.event)
        taken = GiftClaim.objects.filter(gift=gift).count()
        already_mine = GiftClaim.objects.filter(gift=gift, guest=guest).exists()
        if already_mine:
            continue
        if taken >= gift.quantity:
            unavailable.append(gift)
        else:
            locked_gifts.append(gift)
    if unavailable:
        raise GiftUnavailableError(unavailable)

    try:
        for gift in locked_gifts:
            GiftClaim.objects.create(gift=gift, guest=guest)
    except IntegrityError:  # double soumission du même invité
        raise GiftUnavailableError(locked_gifts)

    guest.status = status
    guest.companions = companions if status == Guest.Status.CONFIRMED else 0
    guest.wants_gift = bool(wants_gift) if status == Guest.Status.CONFIRMED and guest.event.gifts.exists() else None
    guest.replied_at = timezone.now()
    guest.save(update_fields=["status", "companions", "wants_gift", "replied_at"])
    return guest
