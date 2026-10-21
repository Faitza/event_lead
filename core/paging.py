"""Longues listes découpées en pages (point 13 de docs/solidite.md)."""
from django.core.paginator import Paginator


def paginate(request, items, per_page, param="page"):
    """Renvoie la page demandée (?page=N). Un numéro absent ou invalide donne la première ou la dernière page."""
    return Paginator(items, per_page).get_page(request.GET.get(param))
