from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def role_required(*roles):
    """Restreint une vue aux utilisateurs connectes ayant l'un des roles donnes.

    Un superutilisateur Django est toujours considere comme administrateur.
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if "admin" in roles and user.is_admin_role:
                return view_func(request, *args, **kwargs)
            if user.role in roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("Acces reserve.")

        return _wrapped

    return decorator


admin_required = role_required("admin")


def vip_organizer_required(view_func):
    """Portail organisateur : role organisateur ET paiement VIP confirme."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if user.is_admin_role:
            return view_func(request, *args, **kwargs)
        if not user.is_organizer:
            raise PermissionDenied("Acces reserve aux organisateurs.")
        if not user.is_vip:
            messages.info(request, "Finalisez votre paiement pour activer votre acces Organisateur VIP.")
            return redirect("payments:vip")
        return view_func(request, *args, **kwargs)

    return _wrapped
