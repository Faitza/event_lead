from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render

from .models import Ad


def ad_click(request, pk):
    """Incrémente les clics puis redirige vers le site du sponsor."""
    ad = get_object_or_404(Ad, pk=pk, is_active=True)
    Ad.objects.filter(pk=ad.pk).update(clicks=F("clicks") + 1)
    return redirect(ad.sponsor_link)


def ad_list(request):
    """Publicités actives, consultables par les organisateurs et les invités."""
    ads = Ad.objects.filter(is_active=True)
    Ad.objects.filter(pk__in=[a.pk for a in ads]).update(views=F("views") + 1)
    return render(request, "ads/list.html", {"ads": ads})
