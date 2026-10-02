from django import template

register = template.Library()


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
