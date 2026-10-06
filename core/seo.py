"""Pour Google et les autres moteurs : /robots.txt (ce qu'ils peuvent lire) et /sitemap.xml (la liste des pages publiques).

Les adresses sont construites avec le domaine de la requête (https://... en ligne), sans rien à régler.
Les chemins interdits sont les mêmes que les pages marquées « noindex » (core/context_processors.py).
"""
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import escape
from django.views.decorators.http import require_GET

from events.models import Event

from .context_processors import PRIVATE_PREFIXES

PUBLIC_PAGES = [
    ("core:landing", "daily", "1.0"),
    ("events:explore", "daily", "0.9"),
    ("payments:ticketing", "daily", "0.9"),
    ("core:help", "monthly", "0.6"),
    ("core:privacy", "yearly", "0.3"),
    ("core:terms", "yearly", "0.3"),
]


def _origin(request):
    return f"{request.scheme}://{request.get_host()}"


@require_GET
def robots_txt(request):
    lines = ["User-agent: *"]
    lines += [f"Disallow: {prefix}" for prefix in PRIVATE_PREFIXES]
    lines += ["Disallow: /billetterie/*/payer/", "Allow: /", "", f"Sitemap: {_origin(request)}{reverse('sitemap')}", ""]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


@require_GET
def sitemap_xml(request):
    origin = _origin(request)
    entries = [(origin + reverse(name), None, freq, prio) for name, freq, prio in PUBLIC_PAGES]
    for event in Event.objects.public_active().upcoming().only("pk", "created_at")[:1000]:
        entries.append((origin + event.get_absolute_url(), event.created_at.date(), "weekly", "0.8"))
    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, freq, prio in entries:
        body.append("  <url><loc>%s</loc>%s<changefreq>%s</changefreq><priority>%s</priority></url>" % (
            escape(loc), f"<lastmod>{lastmod.isoformat()}</lastmod>" if lastmod else "", freq, prio))
    body.append("</urlset>")
    return HttpResponse("\n".join(body) + "\n", content_type="application/xml; charset=utf-8")
