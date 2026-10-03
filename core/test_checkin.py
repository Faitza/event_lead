"""Tests du QR code d'entrée (invité) et du pointage du jour J (équipe)."""
import re
from datetime import time, timedelta

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from events import checkin
from events.models import CheckIn, Event, Guest, new_entry_code, normalize_entry_code

PASSWORD = "MotDePasse-Solide-42"


def make_event(**kw):
    defaults = dict(title="Gala des Fondateurs", event_type="private", date=timezone.localdate(), time=time(18, 0),
                    venue="Pétion-Ville", max_guests=50, allow_companions=True, max_companions=3)
    defaults.update(kw)
    return Event.objects.create(**defaults)


def make_user(email, role="guest"):
    return CustomUser.objects.create_user(username=email, email=email, password=PASSWORD, role=role)


class EntryCodeTests(TestCase):
    def test_every_guest_gets_a_unique_readable_code(self):
        event = make_event()
        codes = {Guest.objects.create(event=event, name=f"Invité {i}").entry_code for i in range(30)}
        self.assertEqual(len(codes), 30)
        for code in codes:
            self.assertRegex(code, r"^EL-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$")

    def test_code_is_kept_when_the_guest_is_saved_again(self):
        guest = Guest.objects.create(event=make_event(), name="Carla")
        code = guest.entry_code
        guest.name = "Carla Joseph"
        guest.save()
        guest.refresh_from_db()
        self.assertEqual(guest.entry_code, code)

    def test_codes_are_normalised(self):
        self.assertEqual(normalize_entry_code("el-7k4q-92md"), "EL-7K4Q-92MD")
        self.assertEqual(normalize_entry_code(" EL 7K4Q 92MD "), "EL-7K4Q-92MD")
        self.assertEqual(normalize_entry_code("EL7K4Q92MD"), "EL-7K4Q-92MD")
        self.assertRegex(new_entry_code(), r"^EL-\w{4}-\w{4}$")


class TicketPageTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.guest = Guest.objects.create(event=self.event, name="Guerline Pierre", status="confirmed", companions=1,
                                          replied_at=timezone.now())

    def url(self, name):
        return reverse(f"events:{name}", args=[self.guest.magic_token])

    def test_confirmed_guest_sees_the_ticket_without_logging_in(self):
        r = self.client.get(self.url("invitation_ticket"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "<svg")
        self.assertContains(r, self.guest.entry_code)
        self.assertContains(r, "Guerline Pierre")
        self.assertContains(r, "2 personnes (avec 1 accompagnant)")
        self.assertNotIn(reverse("accounts:login"), r.content.decode())

    def test_ticket_is_only_for_guests_who_confirmed(self):
        for status in ("pending", "maybe", "declined"):
            Guest.objects.filter(pk=self.guest.pk).update(status=status)
            r = self.client.get(self.url("invitation_ticket"))
            self.assertRedirects(r, self.guest.get_invitation_url(), fetch_redirect_response=False)

    def test_png_download(self):
        r = self.client.get(self.url("invitation_ticket_png"))
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertTrue(r.content.startswith(b"\x89PNG"))
        self.assertIn(self.guest.entry_code, r["Content-Disposition"])

    def test_ticket_in_each_language(self):
        for code, word in (("en", "Your entry ticket"), ("ht", "Biyè antre w la"), ("fr", "Votre billet d")):
            r = self.client.get(self.url("invitation_ticket") + f"?lang={code}")
            self.assertContains(r, word)

    def test_confirmation_page_offers_the_qr_code_to_confirmed_guests_only(self):
        r = self.client.get(self.url("invitation_done"))
        self.assertContains(r, self.guest.get_ticket_url())
        Guest.objects.filter(pk=self.guest.pk).update(status="declined")
        r = self.client.get(self.url("invitation_done"))
        self.assertNotContains(r, self.guest.get_ticket_url())

    def test_answered_page_links_to_the_ticket(self):
        r = self.client.get(self.guest.get_invitation_url())
        self.assertContains(r, self.guest.get_ticket_url())

    def test_public_entry_page_shows_nothing_about_the_guest(self):
        r = self.client.get(reverse("events:entry_code", args=[self.guest.entry_code]))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Guerline")
        self.assertNotContains(r, "Valider l")

    def test_staff_validates_from_the_qr_address(self):
        self.client.login(email=make_user("a@x.ht", "admin").email, password=PASSWORD)
        url = reverse("events:entry_code", args=[self.guest.entry_code.lower()])
        self.assertContains(self.client.get(url), "Guerline Pierre")
        r = self.client.post(url)
        self.assertContains(r, "Entrée validée")
        self.guest.refresh_from_db()
        self.assertIsNotNone(self.guest.checked_in_at)
        self.assertContains(self.client.get(url), "Déjà pointé")


class CheckInServiceTests(TestCase):
    def setUp(self):
        self.admin = make_user("a@x.ht", "admin")
        self.event = make_event()
        self.guest = Guest.objects.create(event=self.event, name="Ronald", status="confirmed", replied_at=timezone.now())

    def test_valid_scan_then_duplicate(self):
        first = checkin.scan(self.event, self.guest.entry_code, self.admin)
        self.assertEqual(first.result, "validated")
        self.guest.refresh_from_db()
        arrived = self.guest.checked_in_at
        self.assertIsNotNone(arrived)
        second = checkin.scan(self.event, self.guest.entry_code, self.admin)
        self.assertEqual(second.result, "duplicate")
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.checked_in_at, arrived)
        self.assertEqual(self.event.check_ins.filter(result="duplicate").count(), 1)

    def test_scan_accepts_the_full_address_or_a_hand_typed_code(self):
        self.assertEqual(checkin.scan(self.event, f"https://eventlead.ht/entree/{self.guest.entry_code}/?x=1", self.admin).result, "validated")
        other = Guest.objects.create(event=self.event, name="Autre", status="confirmed")
        typed = other.entry_code.replace("-", "").lower()
        self.assertEqual(checkin.scan(self.event, typed, self.admin).result, "validated")

    def test_unknown_code_is_refused_and_logged(self):
        outcome = checkin.scan(self.event, "EL-ZZZZ-ZZZZ", self.admin)
        self.assertEqual(outcome.result, "unknown")
        self.assertEqual(self.event.check_ins.get().result, "unknown")

    def test_code_of_another_event_is_refused(self):
        other_event = make_event(title="Autre soirée")
        stranger = Guest.objects.create(event=other_event, name="Étrangère", status="confirmed")
        outcome = checkin.scan(self.event, stranger.entry_code, self.admin)
        self.assertEqual(outcome.result, "wrong_event")
        stranger.refresh_from_db()
        self.assertIsNone(stranger.checked_in_at)
        self.assertEqual(checkin.describe(outcome)["detail"], "Ce billet est pour « Autre soirée ».")

    def test_unconfirmed_guest_is_let_in_with_a_note(self):
        Guest.objects.filter(pk=self.guest.pk).update(status="maybe")
        self.guest.refresh_from_db()
        info = checkin.describe(checkin.scan(self.event, self.guest.entry_code, self.admin))
        self.assertEqual(info["tone"], "success")
        self.assertIn("Peut-être", info["note"])

    def test_walk_in_is_created_present_and_checked_in(self):
        outcome = checkin.add_walk_in(self.event, "Marc Voisin", 2, "+509 3000 0000", self.admin)
        guest = outcome.guest
        self.assertTrue(guest.added_on_site)
        self.assertEqual(guest.status, "confirmed")
        self.assertIsNotNone(guest.checked_in_at)
        self.assertEqual(guest.party_size, 3)
        self.assertEqual(outcome.result, "walk_in")

    def test_walk_in_ignores_the_guest_limit(self):
        small = make_event(max_guests=1)
        Guest.objects.create(event=small, name="Premier")
        checkin.add_walk_in(small, "Deuxième", 0, "", self.admin)
        self.assertEqual(small.guests.count(), 2)

    def test_cancel_makes_the_guest_expected_again(self):
        checkin.scan(self.event, self.guest.entry_code, self.admin)
        self.assertIsNotNone(checkin.cancel_check_in(self.event, self.guest, self.admin))
        self.guest.refresh_from_db()
        self.assertIsNone(self.guest.checked_in_at)
        self.assertEqual(checkin.scan(self.event, self.guest.entry_code, self.admin).result, "validated")

    def test_stats(self):
        for i in range(4):
            Guest.objects.create(event=self.event, name=f"G{i}", status="confirmed", companions=1 if i == 0 else 0)
        Guest.objects.create(event=self.event, name="Peut-être", status="maybe")
        confirmed = list(self.event.guests.filter(status="confirmed"))
        checkin.scan(self.event, confirmed[0].entry_code, self.admin)
        checkin.scan(self.event, confirmed[1].entry_code, self.admin)
        checkin.scan(self.event, confirmed[1].entry_code, self.admin)  # refusé : déjà utilisé
        checkin.scan(self.event, "EL-AAAA-BBBB", self.admin)  # refusé : inconnu
        checkin.add_walk_in(self.event, "Sur place", 0, "", self.admin)
        s = checkin.stats(self.event)
        self.assertEqual(s["confirmed"], 6)  # 5 confirmés + 1 ajouté sur place
        self.assertEqual(s["arrived"], 3)
        self.assertEqual(s["expected"], 3)
        self.assertEqual(s["refused"], 2)
        self.assertEqual(s["on_site"], 1)
        self.assertEqual(s["percent"], 50)
        self.assertEqual(s["people"], s["arrived"] + sum(g.companions for g in self.event.guests.filter(checked_in_at__isnull=False)))

    def test_describe_in_each_language(self):
        from django.utils import translation

        outcome = checkin.scan(self.event, self.guest.entry_code, self.admin)
        for code, title in (("fr", "Entrée validée"), ("en", "Entry validated"), ("ht", "Antre valide")):
            with translation.override(code):
                self.assertEqual(checkin.describe(outcome)["title"], title)


class CheckInPageTests(TestCase):
    def setUp(self):
        self.admin = make_user("a@x.ht", "admin")
        self.event = make_event()
        self.guest = Guest.objects.create(event=self.event, name="Wilfrid Étienne", status="confirmed", companions=1,
                                          replied_at=timezone.now())
        self.client.login(email="a@x.ht", password=PASSWORD)

    def url(self, name, *args):
        return reverse(f"dashboard:{name}", args=[self.event.pk, *args])

    def test_pages_are_for_the_team_only(self):
        for client_user in (None, make_user("g@x.ht", "guest")):
            self.client.logout()
            if client_user:
                self.client.login(email=client_user.email, password=PASSWORD)
            r = self.client.get(self.url("checkin_event"))
            self.assertIn(r.status_code, (302, 403))
            r = self.client.post(self.url("checkin_scan"), {"code": self.guest.entry_code})
            self.assertIn(r.status_code, (302, 403))
        self.guest.refresh_from_db()
        self.assertIsNone(self.guest.checked_in_at)

    def test_index_and_event_pages(self):
        r = self.client.get(reverse("dashboard:checkin_index"))
        self.assertContains(r, "Gala des Fondateurs")
        self.assertContains(r, "Aujourd")
        r = self.client.get(self.url("checkin_event"))
        self.assertContains(r, "Pointage de l")
        self.assertContains(r, "Pointage ouvert")
        self.assertContains(self.client.get(reverse("dashboard:event_detail", args=[self.event.pk])), reverse("dashboard:checkin_event", args=[self.event.pk]))

    def test_not_today_shows_a_note_but_works(self):
        Event.objects.filter(pk=self.event.pk).update(date=timezone.localdate() + timedelta(days=9))
        r = self.client.get(self.url("checkin_event"))
        self.assertContains(r, "pas lieu aujourd")
        self.assertNotContains(r, "Pointage ouvert")

    def test_scan_endpoint_returns_json(self):
        r = self.client.post(self.url("checkin_scan"), {"code": self.guest.entry_code})
        data = r.json()
        self.assertEqual(data["result"], "validated")
        self.assertEqual(data["name"], "Wilfrid Étienne")
        self.assertEqual(data["tone"], "success")
        again = self.client.post(self.url("checkin_scan"), {"code": self.guest.entry_code}).json()
        self.assertEqual(again["result"], "duplicate")
        self.assertEqual(again["tone"], "warning")
        self.assertEqual(self.client.post(self.url("checkin_scan"), {"code": "n'importe quoi"}).json()["result"], "unknown")

    def test_scan_needs_post(self):
        self.assertEqual(self.client.get(self.url("checkin_scan")).status_code, 405)

    def test_manual_check_in_and_search(self):
        found = self.client.get(self.url("checkin_search"), {"q": "wilfr"}).json()["results"]
        self.assertEqual([g["name"] for g in found], ["Wilfrid Étienne"])
        self.assertFalse(found[0]["arrived"])
        self.assertEqual(self.client.get(self.url("checkin_search"), {"q": "w"}).json()["results"], [])
        r = self.client.post(self.url("checkin_manual"), {"guest": self.guest.pk}).json()
        self.assertEqual(r["result"], "validated")
        self.assertTrue(self.client.get(self.url("checkin_search"), {"q": self.guest.entry_code}).json()["results"][0]["arrived"])

    def test_manual_check_in_cannot_reach_another_event(self):
        stranger = Guest.objects.create(event=make_event(title="Autre"), name="Autre invité")
        self.assertEqual(self.client.post(self.url("checkin_manual"), {"guest": stranger.pk}).status_code, 404)

    def test_walk_in_endpoint(self):
        r = self.client.post(self.url("checkin_walk_in"), {"name": "  Marc Voisin ", "companions": "2", "phone": ""})
        self.assertEqual(r.json()["result"], "walk_in")
        guest = Guest.objects.get(name="Marc Voisin")
        self.assertEqual((guest.companions, guest.added_on_site), (2, True))
        self.assertEqual(self.client.post(self.url("checkin_walk_in"), {"name": "  "}).status_code, 400)
        self.client.post(self.url("checkin_walk_in"), {"name": "Négatif", "companions": "-5"})
        self.assertEqual(Guest.objects.get(name="Négatif").companions, 0)

    def test_cancel_endpoint(self):
        self.client.post(self.url("checkin_scan"), {"code": self.guest.entry_code})
        r = self.client.post(self.url("checkin_cancel", self.guest.pk))
        self.assertTrue(r.json()["cancelled"])
        self.guest.refresh_from_db()
        self.assertIsNone(self.guest.checked_in_at)
        self.assertEqual(self.client.get(self.url("checkin_cancel", self.guest.pk)).status_code, 405)

    def test_live_fragment_has_stats_and_latest_arrivals(self):
        self.client.post(self.url("checkin_scan"), {"code": self.guest.entry_code})
        self.client.post(self.url("checkin_scan"), {"code": "EL-AAAA-BBBB"})
        html = self.client.get(self.url("checkin_live")).content.decode()
        self.assertIn('data-slot="stats"', html)
        self.assertIn("Wilfrid Étienne", html)
        self.assertIn("1 sur 1 invités confirmés", html)
        self.assertIn("100 %", html)
        self.assertRegex(html, r'data-result="unknown" data-refused="1"')

    def test_page_in_each_language(self):
        for code in ("en", "ht"):
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = code
            for name in ("checkin_event",):
                r = self.client.get(self.url(name))
                self.assertContains(r, f'<html lang="{code}"')
                self.assertNotContains(r, "Pointage de l")
        self.assertContains(self.client.get(self.url("checkin_event")), "Kontwòl antre a")

    def test_sidebar_links_to_the_check_in(self):
        self.assertContains(self.client.get(reverse("dashboard:home")), reverse("dashboard:checkin_index"))
