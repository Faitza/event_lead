"""Listes publiques : un groupe d'événements est présenté comme une seule carte."""
from .models import Event


def group_events(events):
    """Transforme une liste d'événements (triée par date) en cartes.

    Un événement sans groupe donne une carte « event » ; les événements d'un même groupe donnent une
    seule carte « group », placée à la date de son premier événement.
    """
    cards, groups = [], {}
    for event in events:
        if event.group_id is None:
            cards.append({"kind": "event", "event": event})
        elif event.group_id in groups:
            groups[event.group_id]["events"].append(event)
        else:
            card = {"kind": "group", "group": event.group, "events": [event]}
            groups[event.group_id] = card
            cards.append(card)
    for card in cards:
        if card["kind"] == "group":
            group, first = card["group"], card["events"][0]
            card["cover_url"] = group.cover_image.url if group.cover_image else first.cover_url
            card["first_date"] = first.date
            card["count"] = len(card["events"])
    return cards


def public_cards(limit=None):
    """Événements publics à venir, regroupés par groupe."""
    events = Event.objects.public_active().upcoming().select_related("group")
    cards = group_events(events)
    return cards[:limit] if limit else cards
