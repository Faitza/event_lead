import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(path):
    """Adresse d'un fichier statique avec sa date de modification (?v=...).

    Le navigateur garde le CSS et le JS en cache : sans ce numéro, une modification du site
    (fond, couleurs, menu) peut rester invisible tant qu'on n'a pas vidé le cache. Le numéro
    change dès que le fichier change, donc le navigateur recharge tout seul.
    """
    url = static(path)
    found = finders.find(path)
    if isinstance(found, (list, tuple)):
        found = found[0] if found else None
    try:
        return "%s?v=%d" % (url, os.stat(found).st_mtime) if found else url
    except (OSError, TypeError):
        return url


@register.filter
def add_class(field, css):
    """Ajoute des classes CSS au widget d'un champ de formulaire."""
    widget = field.field.widget
    existing = widget.attrs.get("class", "")
    input_type = getattr(widget, "input_type", "")
    if not css:
        css = "form-select" if input_type == "select" else "form-control"
    return field.as_widget(attrs={"class": f"{existing} {css}".strip()})


@register.simple_tag(takes_context=True)
def active(context, *prefixes):
    """Renvoie 'active' si le chemin courant commence par l'un des préfixes d'URL."""
    path = context["request"].path
    return "active" if any(path.startswith(p) for p in prefixes) else ""


@register.simple_tag(takes_context=True)
def query_with(context, **kwargs):
    """Reconstruit la query string en remplaçant certaines valeurs."""
    params = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()


@register.filter
def percent(value, total):
    try:
        return round(int(value) * 100 / int(total)) if int(total) else 0
    except (TypeError, ValueError):
        return 0


@register.filter
def stars_range(value):
    return range(1, 6)


def _grouped(value, decimals=0):
    """Nombre avec séparateurs : « 25 000 » en français et en créole, « 25,000 » en anglais (comme les scripts de la page)."""
    from decimal import Decimal, InvalidOperation

    from django.utils.translation import get_language

    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return value
    english = (get_language() or "fr").startswith("en")
    text = f"{number:,.{decimals}f}"  # 25,000.50
    if english:
        return text
    return text.replace(",", " ").replace(".", ",")


@register.filter
def htg(value):
    """Montant en gourdes sans décimales, avec séparateurs de milliers selon la langue."""
    return _grouped(value, 0)


@register.filter
def usd(value):
    """Montant en dollars à deux décimales, avec séparateurs selon la langue."""
    return _grouped(value, 2)
