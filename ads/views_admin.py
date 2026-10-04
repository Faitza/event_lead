from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from core.paging import paginate

from .forms import AdForm
from .models import Ad


@admin_required
def ad_list(request):
    ads = Ad.objects.all()
    totals = ads.aggregate(views=Sum("views"), clicks=Sum("clicks"))
    totals["views"] = totals["views"] or 0
    totals["clicks"] = totals["clicks"] or 0
    totals["ctr"] = round(totals["clicks"] * 100 / totals["views"], 1) if totals["views"] else 0
    page = paginate(request, ads, 25)
    return render(request, "dashboard/ads/list.html", {"ads": page.object_list, "page_obj": page, "totals": totals})


@admin_required
def ad_create(request):
    form = AdForm(request.POST or None, request.FILES or None, initial={"icon_name": "bi-megaphone"})
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Publicité créée."))
        return redirect("dashboard:ad_list")
    return render(request, "dashboard/ads/form.html", {"form": form, "is_new": True})


@admin_required
def ad_edit(request, pk):
    ad = get_object_or_404(Ad, pk=pk)
    form = AdForm(request.POST or None, request.FILES or None, instance=ad)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Publicité mise à jour."))
        return redirect("dashboard:ad_list")
    return render(request, "dashboard/ads/form.html", {"form": form, "ad": ad, "is_new": False})


@admin_required
def ad_delete(request, pk):
    ad = get_object_or_404(Ad, pk=pk)
    if request.method == "POST":
        ad.delete()
        messages.success(request, _("Publicité supprimée."))
        return redirect("dashboard:ad_list")
    return render(request, "dashboard/confirm_delete.html", {
        "object": ad, "kind": _("la publicité"), "blocked": False, "cancel_url": reverse("dashboard:ad_list"),
    })


@admin_required
@require_POST
def ad_toggle(request, pk):
    ad = get_object_or_404(Ad, pk=pk)
    field = request.POST.get("field")
    if field in {"is_active", "show_after_reply"}:
        setattr(ad, field, not getattr(ad, field))
        ad.save(update_fields=[field])
    return redirect("dashboard:ad_list")
