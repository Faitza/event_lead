from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from core.middleware import set_language_cookie
from events.models import Guest

from .forms import LoginForm, ProfileForm, RegisterForm
from .models import CustomUser


def _safe_next(request):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return nxt
    return None


def home_url_for(user):
    """Tableau de bord adapté au rôle de l'utilisateur."""
    if user.is_admin_role:
        return reverse("dashboard:home")
    if user.is_organizer:
        return reverse("events:organizer_portal") if user.is_vip else reverse("payments:vip")
    return reverse("accounts:guest_space")


def post_login_url_for(user):
    """Après connexion : l'accueil (défilé des publications, événements et billets).

    L'administrateur arrive sur son tableau de bord et un organisateur non payé
    reste dirigé vers le paiement de l'accès VIP.
    """
    if user.is_admin_role:
        return reverse("dashboard:home")
    if user.is_organizer and not user.is_vip:
        return reverse("payments:vip")
    return reverse("core:landing")


def login_view(request):
    if request.user.is_authenticated:
        return redirect(post_login_url_for(request.user))
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.user, backend="accounts.backends.EmailBackend")
        messages.success(request, _("Bienvenue, %(nom)s.") % {"nom": form.user.display_name})
        return redirect(_safe_next(request) or post_login_url_for(form.user))
    return render(request, "accounts/login.html", {"form": form, "next": _safe_next(request) or ""})


def register_view(request, organizer=False):
    if request.user.is_authenticated:
        return redirect(post_login_url_for(request.user))
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        role = CustomUser.Role.ORGANIZER if organizer else CustomUser.Role.GUEST
        user = form.save(role=role)
        login(request, user, backend="accounts.backends.EmailBackend")
        if organizer:
            messages.info(request, _("Compte créé. Dernière étape : activez votre accès Organisateur VIP."))
            return redirect("payments:vip")
        messages.success(request, _("Votre compte a été créé avec succès."))
        return redirect(_safe_next(request) or post_login_url_for(user))
    return render(request, "accounts/register.html", {"form": form, "organizer": organizer})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, _("Vous êtes déconnecté."))
    return redirect("core:landing")


@login_required
def dispatch_view(request):
    return redirect(home_url_for(request.user))


@login_required
def become_organizer(request):
    """Un invité connecté peut demander à devenir Organisateur VIP (paiement requis)."""
    user = request.user
    if user.is_admin_role:
        return redirect("dashboard:home")
    if request.method == "POST" and user.role == CustomUser.Role.GUEST:
        user.role = CustomUser.Role.ORGANIZER
        user.save(update_fields=["role"])
    if user.is_organizer:
        return redirect("payments:vip")
    return render(request, "accounts/become_organizer.html")


@login_required
def guest_space(request):
    user = request.user
    invitations = (
        Guest.objects.filter(user=user).select_related("event").order_by("event__date")
    )
    return render(request, "accounts/guest_space.html", {"invitations": invitations})


@login_required
def profile_view(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Profil mis à jour."))
        response = redirect("accounts:profile")
        if request.user.language:
            set_language_cookie(response, request.user.language)
        return response
    return render(request, "accounts/profile.html", {"form": form})
