from django.apps import AppConfig
from django.db.models.signals import post_delete, post_save


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Site"

    def ready(self):
        from ads.models import Ad
        from events.models import Event, EventCategory

        from .content_cache import forget
        from .models import Review

        # Le contenu gardé en mémoire (accueil, menu) est oublié dès qu'une de ces données change
        for model in (Event, EventCategory, Ad, Review):
            post_save.connect(forget, sender=model, dispatch_uid=f"content-cache-save-{model.__name__}")
            post_delete.connect(forget, sender=model, dispatch_uid=f"content-cache-delete-{model.__name__}")

        # Inscription avec Google : provenance notée comme pour le formulaire d'inscription
        from allauth.account.signals import user_signed_up

        from .utm import record_signup
        user_signed_up.connect(record_signup, dispatch_uid="utm-signup-google")
