"""Langue de l'interface : lien (?lang=), choix déjà mémorisé, puis langue du profil.

Ordre de priorité : `?lang=xx` dans l'adresse (lien d'invitation envoyé dans la langue de l'invité),
cookie de langue (choix fait avec le sélecteur), langue du profil, langue du navigateur, français.
"""
from django.conf import settings
from django.utils import translation

SUPPORTED = {code for code, _ in settings.LANGUAGES}


class LanguagePreferenceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        remember = None
        asked = request.GET.get("lang")
        user = getattr(request, "user", None)
        if asked in SUPPORTED:
            remember = asked
        elif settings.LANGUAGE_COOKIE_NAME not in request.COOKIES and user is not None and user.is_authenticated:
            if user.language in SUPPORTED:
                remember = user.language
        if remember:
            translation.activate(remember)
            request.LANGUAGE_CODE = translation.get_language()
        response = self.get_response(request)
        if remember:
            set_language_cookie(response, remember)
            response.headers["Content-Language"] = remember
        return response


def set_language_cookie(response, code):
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME, code, max_age=settings.LANGUAGE_COOKIE_AGE,
        path=settings.LANGUAGE_COOKIE_PATH, domain=settings.LANGUAGE_COOKIE_DOMAIN,
        secure=settings.LANGUAGE_COOKIE_SECURE or None, httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
        samesite=settings.LANGUAGE_COOKIE_SAMESITE,
    )
