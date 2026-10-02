from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CustomUser


@receiver(post_save, sender=CustomUser)
def link_existing_invitations(sender, instance, created, **kwargs):
    """Rattache à un nouveau compte (e-mail ou Google) les invitations déjà envoyées à son e-mail."""
    if created and instance.email:
        from events.models import Guest

        Guest.objects.filter(email__iexact=instance.email, user__isnull=True).update(user=instance)
