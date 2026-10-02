"""Listes publiques d'événements, filtrables par catégorie (?categorie=<identifiant>)."""
from .models import Event, EventCategory


def public_events_by_category(slug=""):
    """Événements publics à venir, restreints à une catégorie si `slug` en désigne une.

    Seules les catégories qui ont au moins un événement public à venir sont proposées ;
    un identifiant inconnu est ignoré (on affiche alors tout).
    Retourne (événements, catégories proposées, catégorie choisie ou None).
    """
    base = Event.objects.public_active().upcoming().select_related("category")
    categories = list(EventCategory.objects.filter(events__in=base.values("pk")).distinct())
    selected = next((c for c in categories if c.slug == slug), None)
    events = base.filter(category=selected) if selected else base
    return events, categories, selected
