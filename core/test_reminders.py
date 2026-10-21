"""Tests des relances : qui est relancé et quand, envoi par e-mail ou WhatsApp, arrêt à la réponse, maximum de 3, accès équipe."""
from datetime import time, timedelta
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from events import reminders
from events.models import Event, Guest, Reminder

PASSWORD = "MotDePasse-Solide-42"


def make_event(**kw):
    defaults = dict(title="Mariage de Sarah et Jean-Marc", event_type="private", date=timezone.localdate() + timedelta(days=30),
                    time=time(16, 0), venue="Pétion-Ville", max_guests=100)
    defaults.update(kw)
    return Event.objects.create(**defaults)


def make_guest(event, name="Marie-Claude", days_ago=5, **kw):
    defaults = dict(event=event, name=name, email="mc@example.com", phone="+509 3123 9090", sent_via="email",
                    invitation_sent_at=timezone.now() - timedelta(days=days_ago))
    defaults.update(kw)
    return Guest.objects.create(**defaults)


def remind_at(guest, days_ago, channel="email"):
    return Reminder.objects.create(guest=guest, channel=channel, sent_at=timezone.now() - timedelta(days=days_ago))


def make_user(email, role="guest"):
    return CustomUser.objects.create_user(username=email, email=email, password=PASSWORD, role=role)


def row_for(event, guest):
    return next(r for r in reminders.overview(event) if r.guest.pk == guest.pk)


class WhoIsDueTests(TestCase):
    def setUp(self):
        self.event = make_event()  # première relance 3 jours après l'invitation, puis tous les 7 jours, 3 au plus

    def test_first_reminder_comes_after_the_chosen_delay(self):
        recent = make_guest(self.event, "Récent", days_ago=2)
        old = make_guest(self.event, "Ancien", days_ago=3)
        self.assertEqual(row_for(self.event, recent).state, reminders.WAITING)
        self.assertEqual(row_for(self.event, old).state, reminders.DUE)
        self.event.reminder_first_after_days = 7
        self.assertEqual(row_for(self.event, old).state, reminders.WAITING)

    def test_next_reminders_follow_the_chosen_frequency(self):
        guest = make_guest(self.event, days_ago=20)
        remind_at(guest, 3)
        row = row_for(self.event, guest)
        self.assertEqual((row.count, row.state), (1, reminders.WAITING))
        self.assertEqual(row.due_on, timezone.localdate() + timedelta(days=4))
        Reminder.objects.all().delete()
        remind_at(guest, 7)
        self.assertEqual(row_for(self.event, guest).state, reminders.DUE)
        self.event.reminder_every_days = 3
        Reminder.objects.all().delete()
        remind_at(guest, 3)
        self.assertEqual(row_for(self.event, guest).state, reminders.DUE)

    def test_guests_who_replied_are_never_listed(self):
        for status in ("confirmed", "declined", "maybe"):
            make_guest(self.event, f"Répondu {status}", status=status, replied_at=timezone.now())
        pending = make_guest(self.event, "Sans réponse")
        self.assertEqual([r.guest.pk for r in reminders.overview(self.event)], [pending.pk])

    def test_a_guest_who_has_not_been_invited_yet_is_not_remindable(self):
        guest = make_guest(self.event, invitation_sent_at=None)
        row = row_for(self.event, guest)
        self.assertEqual(row.state, reminders.NOT_INVITED)
        with self.assertRaises(reminders.ReminderError):
            reminders.remind_guest(self.event, guest)
        self.assertEqual(Reminder.objects.count(), 0)

    def test_maximum_is_three_even_when_asked_by_hand(self):
        guest = make_guest(self.event, days_ago=60)
        self.event.reminder_max = 3
        for days in (30, 20, 10):
            remind_at(guest, days)
        self.assertEqual(row_for(self.event, guest).state, reminders.MAXED)
        with self.assertRaises(reminders.ReminderError):
            reminders.remind_guest(self.event, guest)
        self.assertEqual(guest.reminders.count(), 3)
        # Même un réglage trafiqué à 9 ne dépasse jamais 3
        Event.objects.filter(pk=self.event.pk).update(reminder_max=9)
        self.event.refresh_from_db()
        self.assertEqual(reminders.limit_for(self.event), 3)
        with self.assertRaises(reminders.ReminderError):
            reminders.remind_guest(self.event, guest)

    def test_lower_maximum_stops_earlier(self):
        self.event.reminder_max = 1
        guest = make_guest(self.event, days_ago=30)
        remind_at(guest, 10)
        self.assertEqual(row_for(self.event, guest).state, reminders.MAXED)

    def test_channel_is_the_one_of_the_invitation_with_a_fallback(self):
        both_email = make_guest(self.event, "A", sent_via="email")
        both_wa = make_guest(self.event, "B", sent_via="whatsapp")
        email_only = make_guest(self.event, "C", sent_via="whatsapp", phone="")
        phone_only = make_guest(self.event, "D", sent_via="email", email="")
        nobody = make_guest(self.event, "E", email="", phone="")
        self.assertEqual(reminders.effective_channel(both_email), "email")
        self.assertEqual(reminders.effective_channel(both_wa), "whatsapp")
        self.assertEqual(reminders.effective_channel(email_only), "email")
        self.assertEqual(reminders.effective_channel(phone_only), "whatsapp")
        self.assertEqual(reminders.effective_channel(nobody), "")
        self.assertEqual(row_for(self.event, nobody).state, reminders.NO_CONTACT)

    def test_there_is_no_sms_channel(self):
        self.assertEqual({c for c, _ in Reminder._meta.get_field("channel").choices}, {"email", "whatsapp"})

    def test_stats(self):
        make_guest(self.event, "Jamais", days_ago=5)
        once = make_guest(self.event, "Une fois", days_ago=30)
        remind_at(once, 8)
        twice = make_guest(self.event, "Deux fois", days_ago=40)
        remind_at(twice, 20)
        remind_at(twice, 9)
        make_guest(self.event, "Pas invité", invitation_sent_at=None)
        make_guest(self.event, "Répondu", status="confirmed", replied_at=timezone.now())
        stat = reminders.stats(self.event, reminders.overview(self.event))
        self.assertEqual((stat["total"], stat["no_reply"], stat["invited"], stat["not_invited"]), (5, 4, 3, 1))
        self.assertEqual((stat["never"], stat["reminded"], stat["once"], stat["twice"]), (1, 2, 1, 1))
        self.assertEqual(stat["due"], 3)


class SendingTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.admin = make_user("a@x.ht", "admin")

    def test_email_reminder_is_sent_in_the_language_of_the_guest(self):
        for code, subject, phrase in (
            ("fr", "Rappel : Mariage de Sarah et Jean-Marc", "attendent encore votre réponse"),
            ("en", "Reminder: Mariage de Sarah et Jean-Marc", "are still waiting for your reply"),
            ("ht", "Rapèl : Mariage de Sarah et Jean-Marc", "ap tann repons ou toujou"),
        ):
            guest = make_guest(self.event, f"Invité {code}", language=code, email=f"{code}@example.com")
            self.assertEqual(reminders.remind_guest(self.event, guest, self.admin), "email")
            sent = mail.outbox[-1]
            self.assertEqual(sent.subject, subject)
            self.assertEqual(sent.to, [f"{code}@example.com"])
            self.assertIn(phrase, sent.body)
            self.assertIn(f"/invitation/{guest.magic_token}/?lang={code}", sent.body)
            self.assertEqual(sent.reply_to, ["contact@eventlead.ht"])
        self.assertEqual(Reminder.objects.filter(channel="email", sent_by=self.admin).count(), 3)

    def test_whatsapp_reminder_is_only_recorded_never_sent_by_the_server(self):
        guest = make_guest(self.event, sent_via="whatsapp")
        self.assertEqual(reminders.remind_guest(self.event, guest, self.admin), "whatsapp")
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(guest.reminders.get().channel, "whatsapp")

    def test_whatsapp_link_has_the_message_ready(self):
        from events.messaging import reminder_links

        guest = make_guest(self.event, sent_via="whatsapp", phone="+509 3123 9090")
        links = reminder_links(None, guest)
        self.assertTrue(links["whatsapp"].startswith("https://wa.me/50931239090?text="))
        self.assertIn(str(guest.magic_token), links["whatsapp"])
        self.assertNotIn("sms:", links["whatsapp"])

    def test_a_guest_who_replied_meanwhile_is_not_reminded(self):
        guest = make_guest(self.event)
        Guest.objects.filter(pk=guest.pk).update(status="confirmed", replied_at=timezone.now())
        with self.assertRaises(reminders.ReminderError):
            reminders.remind_guest(self.event, guest, self.admin)
        self.assertEqual((Reminder.objects.count(), len(mail.outbox)), (0, 0))

    def test_double_click_does_not_send_twice(self):
        guest = make_guest(self.event)
        reminders.remind_guest(self.event, guest, self.admin)
        with self.assertRaises(reminders.ReminderError):
            reminders.remind_guest(self.event, guest, self.admin)
        self.assertEqual((Reminder.objects.count(), len(mail.outbox)), (1, 1))

    def test_failed_email_is_not_recorded(self):
        guest = make_guest(self.event)
        with mock.patch("events.reminders.EmailMessage.send", side_effect=OSError("SMTP indisponible")):
            with self.assertRaises(reminders.ReminderError):
                reminders.remind_guest(self.event, guest, self.admin)
        self.assertEqual(Reminder.objects.count(), 0)
        row = row_for(self.event, guest)
        self.assertEqual(row.state, reminders.DUE)

    def test_past_cancelled_and_draft_events_accept_no_reminder(self):
        guest = make_guest(self.event)
        for change in ({"date": timezone.localdate() - timedelta(days=1)}, {"status": "cancelled"}, {"status": "draft"}):
            Event.objects.filter(pk=self.event.pk).update(**change)
            self.event.refresh_from_db()
            with self.assertRaises(reminders.ReminderError):
                reminders.remind_guest(self.event, guest, self.admin)
            self.assertEqual(sum(reminders.send_due_emails(self.event).values()), 0)
            Event.objects.filter(pk=self.event.pk).update(date=timezone.localdate() + timedelta(days=30), status="active")
            self.event.refresh_from_db()
        self.assertEqual((Reminder.objects.count(), len(mail.outbox)), (0, 0))

    def test_send_due_emails_sends_only_what_is_due_by_email(self):
        due_mail = make_guest(self.event, "Due e-mail", days_ago=5, email="due@example.com")
        make_guest(self.event, "Pas encore", days_ago=1, email="wait@example.com")
        make_guest(self.event, "Due WhatsApp", days_ago=5, sent_via="whatsapp")
        make_guest(self.event, "Répondu", days_ago=9, status="confirmed", replied_at=timezone.now())
        result = reminders.send_due_emails(self.event, self.admin)
        self.assertEqual((result[reminders.SENT], result["whatsapp_waiting"], result[reminders.FAILED]), (1, 1, 0))
        self.assertEqual([m.to for m in mail.outbox], [["due@example.com"]])
        self.assertEqual(due_mail.reminders.count(), 1)
        # Un second « Envoyer maintenant » juste après n'envoie plus rien
        self.assertEqual(reminders.send_due_emails(self.event, self.admin)[reminders.SENT], 0)
        self.assertEqual(len(mail.outbox), 1)


class SettingsValidationTests(TestCase):
    def test_valid_values(self):
        values, error = reminders.validate_settings({"first_after": "7", "every": "3", "max": "2", "hour": "9", "auto": "on"})
        self.assertIsNone(error)
        self.assertEqual(values, {"reminder_first_after_days": 7, "reminder_every_days": 3, "reminder_max": 2,
                                  "reminder_hour": 9, "reminders_auto": True})

    def test_invalid_values_are_refused(self):
        good = {"first_after": "3", "every": "7", "max": "3", "hour": "10"}
        for field, bad in (("first_after", "4"), ("every", "0"), ("max", "4"), ("max", "0"), ("hour", "25"), ("hour", "x"), ("every", "")):
            values, error = reminders.validate_settings({**good, field: bad})
            self.assertIsNone(values, (field, bad))
            self.assertTrue(error)
        values, _error = reminders.validate_settings(good)
        self.assertFalse(values["reminders_auto"])


class ReminderPagesTests(TestCase):
    def setUp(self):
        self.admin = make_user("a@x.ht", "admin")
        self.event = make_event()
        self.guest = make_guest(self.event, "Marie-Claude Joseph", days_ago=5)
        self.whatsapp = make_guest(self.event, "Jean-Robert Louis", days_ago=5, sent_via="whatsapp", email="")
        self.client.login(email="a@x.ht", password=PASSWORD)

    def url(self, name, *args):
        return reverse(f"dashboard:{name}", args=[self.event.pk, *args])

    def test_pages_are_for_the_team_only(self):
        for client_user in (None, make_user("g@x.ht", "guest")):
            self.client.logout()
            if client_user:
                self.client.login(email=client_user.email, password=PASSWORD)
            for name, args in (("reminder_event", ()), ("reminder_live", ()), ("reminder_settings", ()), ("reminder_send_due", ()),
                               ("reminder_send_one", (self.guest.pk,))):
                r = self.client.post(self.url(name, *args)) if name != "reminder_event" and name != "reminder_live" else self.client.get(self.url(name, *args))
                self.assertIn(r.status_code, (302, 403), name)
            r = self.client.get(reverse("dashboard:reminder_index"))
            self.assertIn(r.status_code, (302, 403))
        self.assertEqual((Reminder.objects.count(), len(mail.outbox)), (0, 0))

    def test_index_and_event_pages(self):
        r = self.client.get(reverse("dashboard:reminder_index"))
        self.assertContains(r, "Mariage de Sarah et Jean-Marc")
        self.assertContains(r, "2 à relancer")
        r = self.client.get(self.url("reminder_event"))
        self.assertContains(r, "Relancer les invités")
        self.assertContains(r, "Marie-Claude Joseph")
        self.assertContains(r, "Envoyer maintenant · 2")
        self.assertContains(r, "jamais par SMS")
        self.assertContains(r, "https://wa.me/")
        self.assertNotContains(r, "sms:")

    def test_sidebar_has_a_reminders_link(self):
        r = self.client.get(reverse("dashboard:home"))
        self.assertContains(r, reverse("dashboard:reminder_index"))

    def test_live_fragment(self):
        r = self.client.get(self.url("reminder_live"))
        self.assertContains(r, 'data-slot="table"')
        self.assertContains(r, "Jean-Robert Louis")
        self.assertNotContains(r, "<html")

    def test_page_exists_in_three_languages(self):
        for code, heading, button in (
            ("fr", "Relancer les invités", "Relancer"),
            ("en", "Remind the guests", "Remind"),
            ("ht", "Voye rapèl bay envite yo", "Voye rapèl"),
        ):
            r = self.client.get(self.url("reminder_event") + f"?lang={code}")
            self.assertContains(r, heading, msg_prefix=code)
            self.assertContains(r, button, msg_prefix=code)
            if code != "fr":
                self.assertNotContains(r, "Relancer les invités", msg_prefix=code)
                self.assertNotContains(r, "jamais par SMS", msg_prefix=code)

    def test_empty_state(self):
        Guest.objects.all().update(status="confirmed", replied_at=timezone.now())
        r = self.client.get(self.url("reminder_event"))
        self.assertContains(r, "Tous les invités ont répondu")

    def test_settings_are_saved(self):
        r = self.client.post(self.url("reminder_settings"), {"first_after": "7", "every": "14", "max": "2", "hour": "9", "auto": "on"})
        self.assertRedirects(r, self.url("reminder_event"))
        self.event.refresh_from_db()
        self.assertEqual((self.event.reminder_first_after_days, self.event.reminder_every_days, self.event.reminder_max,
                          self.event.reminder_hour, self.event.reminders_auto), (7, 14, 2, 9, True))
        self.client.post(self.url("reminder_settings"), {"first_after": "5", "every": "14", "max": "2", "hour": "9"})
        self.event.refresh_from_db()
        self.assertEqual(self.event.reminder_first_after_days, 7)

    def test_send_one_by_email_and_by_whatsapp(self):
        r = self.client.post(self.url("reminder_send_one", self.guest.pk), HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(r.json(), {"ok": True, "channel": "email", "name": "Marie-Claude Joseph"})
        self.assertEqual(len(mail.outbox), 1)
        r = self.client.post(self.url("reminder_send_one", self.whatsapp.pk))
        self.assertEqual(r.json()["channel"], "whatsapp")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(Reminder.objects.filter(sent_by=self.admin).count(), 2)

    def test_send_one_refused_after_reply(self):
        Guest.objects.filter(pk=self.guest.pk).update(status="declined", replied_at=timezone.now())
        r = self.client.post(self.url("reminder_send_one", self.guest.pk))
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()["ok"])
        self.assertIn("déjà répondu", r.json()["error"])
        self.assertEqual(Reminder.objects.count(), 0)

    def test_send_one_only_for_this_events_guests(self):
        other = make_guest(make_event(title="Autre"), "Étranger")
        r = self.client.post(self.url("reminder_send_one", other.pk))
        self.assertEqual(r.status_code, 404)

    def test_send_now_sends_the_emails_and_tells_about_whatsapp(self):
        r = self.client.post(self.url("reminder_send_due"), HTTP_X_REQUESTED_WITH="fetch")
        data = r.json()
        self.assertEqual((data["sent"], data["waiting"], data["failed"]), (1, 1, 0))
        self.assertIn("1 e-mail de relance envoyé", data["message"])
        self.assertIn("WhatsApp", data["message"])
        self.assertEqual(len(mail.outbox), 1)
        r = self.client.post(self.url("reminder_send_due"), HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(r.json()["sent"], 0)

    def test_reply_by_the_guest_stops_the_reminders(self):
        r = self.client.get(reverse("events:invitation", args=[self.guest.magic_token]))
        self.assertEqual(r.status_code, 200)
        Guest.objects.filter(pk=self.guest.pk).update(status="confirmed", replied_at=timezone.now())
        r = self.client.get(self.url("reminder_event"))
        self.assertNotContains(r, "Marie-Claude Joseph")
        self.assertEqual(reminders.send_due_emails(self.event)[reminders.SENT], 0)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_demo_mode_notice_while_emails_do_not_really_leave(self):
        self.assertContains(self.client.get(self.url("reminder_event")), "Mode démonstration")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend")
    def test_no_demo_notice_with_a_real_mail_service(self):
        self.assertNotContains(self.client.get(self.url("reminder_event")), "Mode démonstration")


class SendRemindersCommandTests(TestCase):
    def setUp(self):
        self.event = make_event(reminders_auto=True, reminder_hour=0)  # heure d'envoi déjà passée
        make_guest(self.event, "Due e-mail", days_ago=5, email="due@example.com")
        make_guest(self.event, "Due WhatsApp", days_ago=5, sent_via="whatsapp")

    def run_command(self, *args):
        out = StringIO()
        call_command("send_reminders", *args, stdout=out)
        return out.getvalue()

    @override_settings(SITE_URL="https://eventlead.example.ht")
    def test_sends_due_emails_only_for_events_with_automatic_sending(self):
        other = make_event(title="Sans envoi automatique")
        make_guest(other, "Autre", days_ago=5, email="other@example.com")
        out = self.run_command()
        self.assertEqual([m.to for m in mail.outbox], [["due@example.com"]])
        self.assertIn("https://eventlead.example.ht/invitation/", mail.outbox[0].body)
        self.assertIn("1 e-mail(s) envoyé(s)", out)
        self.assertEqual(Reminder.objects.get().automatic, True)
        self.assertEqual(Reminder.objects.filter(guest__event=other).count(), 0)
        # Relancé deux fois de suite : la seconde exécution n'envoie plus rien
        self.run_command()
        self.assertEqual(len(mail.outbox), 1)

    def test_dry_run_sends_nothing(self):
        out = self.run_command("--dry-run")
        self.assertIn("1 e-mail(s) partiraient", out)
        self.assertEqual((Reminder.objects.count(), len(mail.outbox)), (0, 0))

    def test_waits_for_the_sending_hour(self):
        Event.objects.filter(pk=self.event.pk).update(reminder_hour=23)
        with mock.patch("core.management.commands.send_reminders.timezone.localtime") as now:
            now.return_value = timezone.now().replace(hour=8)
            out = self.run_command()
        self.assertIn("avant 23 h", out)
        self.assertEqual(len(mail.outbox), 0)
        self.run_command("--any-hour")
        self.assertEqual(len(mail.outbox), 1)

    def test_one_event_only_and_never_a_past_event(self):
        Event.objects.filter(pk=self.event.pk).update(date=timezone.localdate() - timedelta(days=1))
        self.run_command("--event", str(self.event.pk))
        self.assertEqual(len(mail.outbox), 0)
