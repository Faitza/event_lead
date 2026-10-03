"""Envoie les relances par e-mail arrivées à échéance, pour les événements où l'envoi automatique est activé.

À lancer une fois par heure (cron, tâche planifiée) : chaque événement n'envoie qu'à partir de son heure d'envoi.
Les relances WhatsApp ne partent jamais seules : elles restent à envoyer en un clic depuis la page « Relances ».
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from events import reminders
from events.models import Event


class Command(BaseCommand):
    help = "Envoie les relances par e-mail dues (événements avec envoi automatique, à partir de leur heure d'envoi)."

    def add_arguments(self, parser):
        parser.add_argument("--event", type=int, help="Numéro d'un seul événement")
        parser.add_argument("--dry-run", action="store_true", help="Affiche ce qui partirait, sans rien envoyer")
        parser.add_argument("--any-hour", action="store_true", help="Ignore l'heure d'envoi de l'événement")

    def handle(self, *args, **options):
        events = Event.objects.filter(reminders_auto=True, status=Event.Status.ACTIVE)
        if options["event"]:
            events = events.filter(pk=options["event"])
        hour = timezone.localtime().hour
        total = 0
        for event in events:
            if not reminders.event_accepts_reminders(event):
                continue
            if not options["any_hour"] and hour < event.reminder_hour:
                self.stdout.write(f"{event.title} : avant {event.reminder_hour} h, rien envoyé.")
                continue
            if options["dry_run"]:
                due = [r for r in reminders.overview(event) if r.is_due]
                mails = sum(1 for r in due if r.channel == reminders.EMAIL)
                self.stdout.write(f"{event.title} : {mails} e-mail(s) partiraient, {len(due) - mails} relance(s) WhatsApp à la main.")
                continue
            result = reminders.send_due_emails(event, automatic=True)
            total += result[reminders.SENT]
            self.stdout.write(
                f"{event.title} : {result[reminders.SENT]} e-mail(s) envoyé(s), {result[reminders.FAILED]} échec(s), "
                f"{result['whatsapp_waiting']} relance(s) WhatsApp à la main."
            )
        if not options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Terminé : {total} e-mail(s) de relance envoyé(s)."))
