"""QR code d'entrée : l'adresse /entree/<code>/ de l'invité, dessinée en SVG (page) ou en PNG (téléchargement)."""
import io

import segno
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

DARK = "#2C033B"


def entry_url(request, guest):
    return request.build_absolute_uri(reverse("events:entry_code", args=[guest.entry_code]))


def _qr(data):
    # Niveau de correction « Q » : le code reste lisible s'il est abîmé ou mal imprimé
    return segno.make(data, error="q", micro=False)


def qr_svg(data, label=""):
    """SVG en ligne (sans dimension fixe : la page fixe la taille avec le CSS)."""
    svg = _qr(data).svg_inline(scale=1, border=0, dark=DARK, light=None, omitsize=True, svgclass="qr-svg", lineclass=None)
    aria = f'role="img" aria-label="{escape(label)}" shape-rendering="crispEdges"' if label else 'aria-hidden="true" shape-rendering="crispEdges"'
    return mark_safe(svg.replace("<svg ", f"<svg {aria} ", 1))


def qr_png(data, scale=12):
    out = io.BytesIO()
    _qr(data).save(out, kind="png", scale=scale, border=3, dark=DARK, light="#FFFFFF")
    return out.getvalue()
