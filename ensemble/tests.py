"""« Y aller ensemble » : s'afficher, demandes, messages, blocage, signalements et règles de sécurité."""
from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from events.models import Event, Guest

from .models import Block, Listing, MeetRequest, Message, Profile, Report

PASSWORD = "EventLead2026!"


def make_user(email, first="Marie", role=CustomUser.Role.GUEST):
    return CustomUser.objects.create_user(username=email, email=email, password=PASSWORD, first_name=first, role=role)


def make_event(days=10, **extra):
    data = dict(title="Gala de test", event_type=Event.EventType.PUBLIC, date=timezone.localdate() + timedelta(days=days),
                time=time(19, 30), venue="Hôtel Montana")
    data.update(extra)
    return Event.objects.create(**data)


def register(user, event):
    """Inscription « Je participe » à un événement gratuit."""
    return Guest.objects.create(event=event, user=user, name=user.first_name, email=user.email,
                                status=Guest.Status.CONFIRMED, replied_at=timezone.now(), from_ticket=True)


def show(user, event, city="Delmas", registered=True, **flags):
    """S'affiche pour l'événement ; pour un événement gratuit, inscrit d'abord la personne (sauf registered=False)."""
    now = timezone.now()
    if registered and not event.price_htg and not event.guests.filter(user=user).exists():
        register(user, event)
    profile, _ = Profile.objects.get_or_create(user=user, defaults=dict(
        first_name=user.first_name, city=city, about="Bonjour", adult_confirmed_at=now, rules_accepted_at=now))
    return Listing.objects.create(user=user, event=event, **flags)


JOIN_DATA = {"first_name": "Marie", "city": "Pétion-Ville", "about": "J'adore danser.", "wants_company": "on",
             "adult": "on", "rules": "on"}


class JoinTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.marie = make_user("marie@test.ht")

    def test_event_page_shows_the_block_for_public_upcoming_events_only(self):
        r = self.client.get(self.event.get_absolute_url())
        self.assertContains(r, "Y aller ensemble")
        self.assertContains(r, reverse("ensemble:join", args=[self.event.pk]))
        private = make_event(event_type=Event.EventType.PRIVATE)
        admin = make_user("admin@test.ht", role=CustomUser.Role.ADMIN)
        self.client.force_login(admin)
        self.assertNotContains(self.client.get(private.get_absolute_url()), 'id="y-aller-ensemble"')

    def test_login_is_required(self):
        r = self.client.get(reverse("ensemble:join", args=[self.event.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("accounts:login"), r["Location"])

    def test_age_and_rules_are_required(self):
        self.client.force_login(self.marie)
        data = dict(JOIN_DATA)
        del data["adult"]
        r = self.client.post(reverse("ensemble:join", args=[self.event.pk]), data)
        self.assertContains(r, "réservée aux personnes de 18 ans ou plus")
        self.assertFalse(Listing.objects.exists())

    def test_join_creates_profile_and_listing(self):
        self.client.force_login(self.marie)
        r = self.client.post(reverse("ensemble:join", args=[self.event.pk]), JOIN_DATA)
        self.assertRedirects(r, reverse("ensemble:people", args=[self.event.pk]))
        profile = Profile.objects.get(user=self.marie)
        self.assertEqual(profile.city, "Pétion-Ville")
        self.assertIsNotNone(profile.adult_confirmed_at)
        self.assertTrue(Listing.objects.filter(user=self.marie, event=self.event, wants_company=True).exists())

    def test_honeypot_keeps_nothing(self):
        self.client.force_login(self.marie)
        self.client.post(reverse("ensemble:join", args=[self.event.pk]), dict(JOIN_DATA, website="spam"))
        self.assertFalse(Profile.objects.exists())

    def test_past_and_private_events_are_refused(self):
        self.client.force_login(self.marie)
        past = make_event(days=-1)
        private = make_event(event_type=Event.EventType.PRIVATE)
        for event in (past, private):
            self.assertEqual(self.client.get(reverse("ensemble:join", args=[event.pk])).status_code, 404)

    def test_people_page_needs_to_be_listed_first(self):
        self.client.force_login(self.marie)
        r = self.client.get(reverse("ensemble:people", args=[self.event.pk]))
        self.assertRedirects(r, reverse("ensemble:join", args=[self.event.pk]))

    def test_leave_removes_the_listing(self):
        show(self.marie, self.event)
        self.client.force_login(self.marie)
        self.client.post(reverse("ensemble:leave", args=[self.event.pk]))
        self.assertFalse(Listing.objects.exists())


class PeopleAndRequestTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.marie = make_user("marie@test.ht", "Marie")
        self.jessica = make_user("jessica@test.ht", "Jessica")
        show(self.marie, self.event)
        show(self.jessica, self.event, city="Delmas", wants_transport=True)
        self.client.force_login(self.marie)

    def test_people_page_shows_first_name_and_city_but_never_email_or_last_name(self):
        self.jessica.last_name = "Pierre-Louis"
        self.jessica.phone = "+509 3700 1234"
        self.jessica.save()
        r = self.client.get(reverse("ensemble:people", args=[self.event.pk]))
        self.assertContains(r, "Jessica")
        self.assertContains(r, "Delmas")
        self.assertNotContains(r, "jessica@test.ht")
        self.assertNotContains(r, "Pierre-Louis")
        self.assertNotContains(r, "3700 1234")

    def test_filters(self):
        url = reverse("ensemble:people", args=[self.event.pk])
        self.assertContains(self.client.get(url + "?filtre=transport"), "Jessica")
        self.assertNotContains(self.client.get(url + "?filtre=groupe"), "<strong class=\"d-block ya-name\">Jessica")

    def test_send_request_then_accept_then_chat(self):
        url = reverse("ensemble:send_request", args=[self.event.pk, self.jessica.pk])
        self.client.post(url, {"note": "On partage un taxi ?"})
        req = MeetRequest.objects.get()
        self.assertEqual((req.sender, req.receiver, req.status), (self.marie, self.jessica, "pending"))
        # Pas de conversation avant l'acceptation
        self.assertEqual(self.client.get(reverse("ensemble:conversation", args=[req.pk])).status_code, 404)
        self.client.force_login(self.jessica)
        self.assertContains(self.client.get(reverse("ensemble:requests")), "On partage un taxi ?")
        r = self.client.post(reverse("ensemble:answer", args=[req.pk]), {"action": "accept"})
        self.assertRedirects(r, reverse("ensemble:conversation", args=[req.pk]))
        self.client.post(reverse("ensemble:conversation", args=[req.pk]), {"body": "Avec plaisir !"})
        self.assertEqual(Message.objects.get().sender, self.jessica)
        self.client.force_login(self.marie)
        self.assertContains(self.client.get(reverse("ensemble:conversation", args=[req.pk])), "Avec plaisir !")

    def test_only_the_receiver_can_answer(self):
        req = MeetRequest.objects.create(sender=self.marie, receiver=self.jessica, event=self.event)
        r = self.client.post(reverse("ensemble:answer", args=[req.pk]), {"action": "accept"})
        self.assertEqual(r.status_code, 404)

    def test_declined_request_still_looks_waiting_for_the_sender(self):
        req = MeetRequest.objects.create(sender=self.marie, receiver=self.jessica, event=self.event, status="declined")
        r = self.client.get(reverse("ensemble:requests") + "?onglet=envoyees")
        self.assertContains(r, "En attente de réponse")
        self.assertEqual(self.client.get(reverse("ensemble:conversation", args=[req.pk])).status_code, 404)

    def test_note_is_limited(self):
        url = reverse("ensemble:send_request", args=[self.event.pk, self.jessica.pk])
        self.client.post(url, {"note": "x" * 301})
        self.assertFalse(MeetRequest.objects.exists())

    def test_cannot_request_someone_not_listed(self):
        other = make_user("autre@test.ht", "Autre")
        self.client.post(reverse("ensemble:send_request", args=[self.event.pk, other.pk]), {"note": ""})
        self.assertFalse(MeetRequest.objects.exists())

    def test_chat_closes_seven_days_after_the_event(self):
        past = make_event(days=-8)
        req = MeetRequest.objects.create(sender=self.marie, receiver=self.jessica, event=past, status="accepted")
        self.client.post(reverse("ensemble:conversation", args=[req.pk]), {"body": "Encore là ?"})
        self.assertFalse(Message.objects.exists())

    def test_listings_disappear_after_the_event(self):
        past = make_event(days=-1)
        self.assertEqual(self.client.get(reverse("ensemble:people", args=[past.pk])).status_code, 404)


class BlockAndReportTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.marie = make_user("marie@test.ht", "Marie")
        self.ricardo = make_user("ricardo@test.ht", "Ricardo")
        show(self.marie, self.event)
        show(self.ricardo, self.event)
        self.req = MeetRequest.objects.create(sender=self.ricardo, receiver=self.marie, event=self.event, status="accepted")

    def test_block_hides_both_ways_and_stops_the_chat(self):
        self.client.force_login(self.marie)
        self.client.post(reverse("ensemble:block", args=[self.ricardo.pk]))
        self.assertTrue(Block.between(self.marie, self.ricardo))
        self.assertNotContains(self.client.get(reverse("ensemble:people", args=[self.event.pk])), "Ricardo")
        self.client.force_login(self.ricardo)
        self.assertNotContains(self.client.get(reverse("ensemble:people", args=[self.event.pk])), "Marie</strong>")
        self.assertEqual(self.client.post(reverse("ensemble:conversation", args=[self.req.pk]), {"body": "?"}).status_code, 404)
        self.assertFalse(Message.objects.exists())

    def test_report_with_block(self):
        self.client.force_login(self.marie)
        self.client.post(reverse("ensemble:report", args=[self.ricardo.pk]),
                         {"reason": "money", "details": "Il demande une recharge.", "also_block": "on", "event": self.event.pk})
        report = Report.objects.get()
        self.assertEqual((report.reporter, report.reported, report.reason, report.event), (self.marie, self.ricardo, "money", self.event))
        self.assertTrue(Block.between(self.marie, self.ricardo))

    def test_dashboard_reports_are_for_the_team_only(self):
        self.client.force_login(self.marie)
        self.assertEqual(self.client.get(reverse("dashboard:ensemble_reports")).status_code, 403)

    def test_team_decisions(self):
        report = Report.objects.create(reporter=self.marie, reported=self.ricardo, event=self.event, reason="money")
        Message.objects.create(request=self.req, sender=self.ricardo, body="Envoie-moi 500 gourdes MonCash")
        admin = make_user("admin@test.ht", "Admin", role=CustomUser.Role.ADMIN)
        self.client.force_login(admin)
        r = self.client.get(reverse("dashboard:ensemble_reports"))
        self.assertContains(r, "Ricardo")
        self.assertContains(r, "Demande d&#x27;argent")
        self.assertContains(self.client.get(reverse("dashboard:ensemble_report_conversation", args=[report.pk])), "500 gourdes")
        # Avertir
        self.client.post(reverse("dashboard:ensemble_report_action", args=[report.pk]), {"action": "warn"})
        report.refresh_from_db()
        self.assertEqual(report.status, "warned")
        self.assertTrue(Profile.objects.get(user=self.ricardo).show_warning)
        # Retirer de Y aller ensemble
        report2 = Report.objects.create(reporter=self.marie, reported=self.ricardo, reason="harassment")
        self.client.post(reverse("dashboard:ensemble_report_action", args=[report2.pk]), {"action": "remove"})
        self.assertFalse(Listing.objects.filter(user=self.ricardo).exists())
        self.client.force_login(self.ricardo)
        self.assertRedirects(self.client.get(reverse("ensemble:join", args=[self.event.pk])), self.event.get_absolute_url(), fetch_redirect_response=False)
        # Suspendre puis réactiver
        self.client.force_login(admin)
        report3 = Report.objects.create(reporter=self.marie, reported=self.ricardo, reason="fake")
        self.client.post(reverse("dashboard:ensemble_report_action", args=[report3.pk]), {"action": "suspend"})
        self.ricardo.refresh_from_db()
        self.assertFalse(self.ricardo.is_active)
        self.client.post(reverse("dashboard:ensemble_report_action", args=[report3.pk]), {"action": "reactivate"})
        self.ricardo.refresh_from_db()
        self.assertTrue(self.ricardo.is_active)

    def test_team_account_cannot_be_suspended(self):
        admin = make_user("admin@test.ht", "Admin", role=CustomUser.Role.ADMIN)
        report = Report.objects.create(reporter=self.marie, reported=admin, reason="other")
        self.client.force_login(admin)
        self.client.post(reverse("dashboard:ensemble_report_action", args=[report.pk]), {"action": "suspend"})
        admin.refresh_from_db()
        self.assertTrue(admin.is_active)


class PagesTests(TestCase):
    def test_pages_are_private_for_search_engines(self):
        self.assertContains(self.client.get("/robots.txt"), "Disallow: /ensemble/")

    def test_pages_render_in_three_languages(self):
        event = make_event()
        marie = make_user("marie@test.ht", "Marie")
        jessica = make_user("jessica@test.ht", "Jessica")
        show(marie, event)
        show(jessica, event)
        req = MeetRequest.objects.create(sender=jessica, receiver=marie, event=event, status="accepted")
        self.client.force_login(marie)
        urls = [reverse("ensemble:people", args=[event.pk]), reverse("ensemble:join", args=[event.pk]),
                reverse("ensemble:requests"), reverse("ensemble:conversation", args=[req.pk]), reverse("accounts:guest_space"),
                event.get_absolute_url()]
        expected = {"fr": "Y aller ensemble", "en": "Go together", "ht": "Ale ansanm"}
        for lang, word in expected.items():
            self.client.cookies["django_language"] = lang
            for url in urls:
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200, f"{url} {lang}")
                self.assertContains(r, word, msg_prefix=f"{url} {lang}")


class PhotoTests(TestCase):
    def test_photo_is_resized_and_shown(self):
        import io
        import shutil
        import tempfile

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings
        from PIL import Image

        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        buffer = io.BytesIO()
        Image.new("RGB", (1600, 1200), (120, 20, 90)).save(buffer, "JPEG")
        event = make_event()
        marie = make_user("marie@test.ht")
        self.client.force_login(marie)
        with override_settings(MEDIA_ROOT=media):
            photo = SimpleUploadedFile("moi.jpg", buffer.getvalue(), content_type="image/jpeg")
            self.client.post(reverse("ensemble:join", args=[event.pk]), dict(JOIN_DATA, photo=photo))
            profile = Profile.objects.get(user=marie)
            self.assertTrue(profile.photo.name.startswith("ensemble/"))
            with Image.open(profile.photo.path) as img:
                self.assertLessEqual(max(img.size), 600)


class TicketRuleTests(TestCase):
    """Entrée payante : il faut un billet payé pour proposer à quelqu'un d'y aller ensemble."""

    def setUp(self):
        from decimal import Decimal
        self.event = make_event(price_htg=Decimal("3500"))
        self.marie = make_user("marie@test.ht", "Marie")
        self.jessica = make_user("jessica@test.ht", "Jessica")
        show(self.marie, self.event)
        show(self.jessica, self.event)
        self.client.force_login(self.marie)
        self.url = reverse("ensemble:send_request", args=[self.event.pk, self.jessica.pk])
        self.pay("success", self.jessica)

    def pay(self, status, user=None):
        from payments.models import Payment
        user = user or self.marie
        return Payment.objects.create(user=user, event=self.event, kind=Payment.Kind.TICKET, method=Payment.Method.MONCASH,
                                      amount_htg=3500, reference=f"T-{status}-{user.pk}", status=status)

    def test_without_ticket_the_request_is_refused_and_the_page_offers_the_ticket(self):
        r = self.client.get(reverse("ensemble:people", args=[self.event.pk]))
        self.assertContains(r, "sans billet, vous n")
        self.assertContains(r, reverse("payments:checkout", args=[self.event.pk]))
        self.assertNotContains(r, 'data-bs-target="#ya-ask"')
        self.client.post(self.url, {"note": "On y va ?"})
        self.assertFalse(MeetRequest.objects.exists())

    def test_pending_or_failed_payment_does_not_count(self):
        self.pay("pending")
        self.pay("failed")
        self.client.post(self.url, {"note": ""})
        self.assertFalse(MeetRequest.objects.exists())

    def test_paid_ticket_allows_the_request(self):
        self.pay("success")
        self.assertContains(self.client.get(reverse("ensemble:people", args=[self.event.pk])), 'data-bs-target="#ya-ask"')
        self.client.post(self.url, {"note": ""})
        self.assertTrue(MeetRequest.objects.exists())

    def test_free_event_needs_registration(self):
        """Entrée gratuite : seules les personnes inscrites avec « Je participe » sont dans la liste et font des demandes."""
        free = make_event()
        show(self.marie, free, registered=False)
        show(self.jessica, free)
        sarah = make_user("sarah@test.ht", "Sarah")
        show(sarah, free, registered=False)
        r = self.client.get(reverse("ensemble:people", args=[free.pk]))
        self.assertContains(r, "Jessica")
        self.assertNotContains(r, "Sarah")
        self.assertContains(r, "Inscription requise pour proposer")
        self.client.post(reverse("ensemble:send_request", args=[free.pk, self.jessica.pk]), {"note": ""})
        self.assertFalse(MeetRequest.objects.filter(event=free).exists())
        register(self.marie, free)
        self.client.post(reverse("ensemble:send_request", args=[free.pk, self.jessica.pk]), {"note": ""})
        self.assertTrue(MeetRequest.objects.filter(event=free, receiver=self.jessica).exists())

    def test_people_without_ticket_are_not_in_the_list(self):
        self.pay("success")
        sarah = make_user("sarah@test.ht", "Sarah")
        show(sarah, self.event)
        r = self.client.get(reverse("ensemble:people", args=[self.event.pk]))
        self.assertContains(r, "Jessica")
        self.assertNotContains(r, "Sarah")
        self.client.post(reverse("ensemble:send_request", args=[self.event.pk, sarah.pk]), {"note": ""})
        self.assertFalse(MeetRequest.objects.filter(receiver=sarah).exists())

    def test_people_without_ticket_receive_no_request(self):
        sarah = make_user("sarah@test.ht", "Sarah")
        show(sarah, self.event)
        req = MeetRequest.objects.create(sender=self.jessica, receiver=sarah, event=self.event, note="Salut")
        self.client.force_login(sarah)
        self.assertNotContains(self.client.get(reverse("ensemble:requests")), "Salut")
        self.client.post(reverse("ensemble:answer", args=[req.pk]), {"action": "accept"})
        req.refresh_from_db()
        self.assertEqual(req.status, "pending")
