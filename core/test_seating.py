"""Tests du plan de table : tables, places, invités avec accompagnants, placement automatique, billet, accès équipe."""
from datetime import time, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from accounts.models import CustomUser
from events import checkin, seating
from events.models import Event, Guest, Table

PASSWORD = "MotDePasse-Solide-42"


def make_event(**kw):
    defaults = dict(title="Mariage de Sarah et Jean-Marc", event_type="private", date=timezone.localdate() + timedelta(days=30),
                    time=time(16, 0), venue="Pétion-Ville", max_guests=100, allow_companions=True, max_companions=5)
    defaults.update(kw)
    return Event.objects.create(**defaults)


def make_guest(event, name, companions=0, status="confirmed", **kw):
    replied = timezone.now() if status != "pending" else None
    return Guest.objects.create(event=event, name=name, companions=companions, status=status, replied_at=replied, **kw)


def make_user(email, role="guest"):
    return CustomUser.objects.create_user(username=email, email=email, password=PASSWORD, role=role)


class TableModelTests(TestCase):
    def setUp(self):
        self.event = make_event()

    def test_label_with_and_without_a_name(self):
        self.assertEqual(Table(event=self.event, number=4).label, "Table 4")
        self.assertEqual(Table(event=self.event, number=1, name="Famille de la mariée").label, "Table 1 · Famille de la mariée")
        with translation.override("en"):
            self.assertEqual(Table(event=self.event, number=4).label, "Table 4")
        with translation.override("ht"):
            self.assertEqual(Table(event=self.event, number=4).label, "Tab 4")

    def test_a_number_is_used_once_per_event_only(self):
        Table.objects.create(event=self.event, number=1)
        Table.objects.create(event=make_event(title="Autre"), number=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Table.objects.create(event=self.event, number=1)

    def test_a_guest_who_is_no_longer_coming_loses_the_seat(self):
        table = Table.objects.create(event=self.event, number=1)
        guest = make_guest(self.event, "Roseline", table=table)
        guest.status = "declined"
        guest.save(update_fields=["status"])
        guest.refresh_from_db()
        self.assertIsNone(guest.table_id)

    def test_a_table_of_another_event_is_dropped_when_the_guest_changes_event(self):
        table = Table.objects.create(event=self.event, number=1)
        guest = make_guest(self.event, "Roseline", table=table)
        guest.event = make_event(title="Autre soirée")
        guest.save()
        guest.refresh_from_db()
        self.assertIsNone(guest.table_id)

    def test_deleting_a_table_keeps_its_guests(self):
        table = Table.objects.create(event=self.event, number=1)
        guest = make_guest(self.event, "Roseline", table=table)
        table.delete()
        guest.refresh_from_db()
        self.assertIsNone(guest.table_id)


class BoardTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.t1 = Table.objects.create(event=self.event, number=1, capacity=6)
        self.t2 = Table.objects.create(event=self.event, number=2, capacity=4, name="Amis")

    def test_companions_take_seats_and_only_confirmed_guests_are_listed(self):
        make_guest(self.event, "Nadège", companions=1, table=self.t1)
        make_guest(self.event, "Jonathan", companions=0, table=self.t1)
        make_guest(self.event, "Roseline", companions=2)
        make_guest(self.event, "Claudine", status="declined")
        make_guest(self.event, "Wilson", status="pending")
        data = seating.board(self.event)
        first = data["tables"][0]
        self.assertEqual((first.taken, first.free, first.full), (3, 3, False))
        self.assertEqual([g.name for g in data["unseated"]], ["Roseline"])
        stats = data["stats"]
        self.assertEqual((stats["tables"], stats["seats"], stats["placed"], stats["free"]), (2, 10, 3, 7))
        self.assertEqual((stats["placed_guests"], stats["unseated"], stats["unseated_people"]), (2, 1, 3))
        self.assertEqual((stats["capacity_min"], stats["capacity_max"]), (4, 6))

    def test_guests_of_another_event_never_appear(self):
        make_guest(make_event(title="Autre"), "Étranger")
        self.assertEqual(seating.board(self.event)["unseated"], [])


class SeatGuestTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.t1 = Table.objects.create(event=self.event, number=1, capacity=4)
        self.t2 = Table.objects.create(event=self.event, number=2, capacity=4)

    def test_a_guest_sits_with_the_companions(self):
        guest = make_guest(self.event, "Nadège", companions=2)
        seating.seat_guest(self.event, guest.pk, self.t1.pk)
        guest.refresh_from_db()
        self.assertEqual(guest.table_id, self.t1.pk)
        self.assertEqual(seating.board(self.event)["tables"][0].taken, 3)

    def test_refused_when_the_party_does_not_fit(self):
        make_guest(self.event, "Déjà là", companions=1, table=self.t1)
        guest = make_guest(self.event, "Trio", companions=2)
        with self.assertRaises(seating.SeatingError) as caught:
            seating.seat_guest(self.event, guest.pk, self.t1.pk)
        self.assertIn("2 libres", str(caught.exception))
        guest.refresh_from_db()
        self.assertIsNone(guest.table_id)
        # Un invité de moins sur la table et le trio rentre à la table voisine
        seating.seat_guest(self.event, guest.pk, self.t2.pk)

    def test_the_last_seat_is_taken_but_not_one_more(self):
        make_guest(self.event, "Un", companions=2, table=self.t1)
        seating.seat_guest(self.event, make_guest(self.event, "Deux").pk, self.t1.pk)
        with self.assertRaises(seating.SeatingError):
            seating.seat_guest(self.event, make_guest(self.event, "Trois").pk, self.t1.pk)

    def test_moving_a_guest_frees_the_old_table_and_re_seating_on_the_same_table_does_not_double_count(self):
        guest = make_guest(self.event, "Quatuor", companions=3)
        seating.seat_guest(self.event, guest.pk, self.t1.pk)
        seating.seat_guest(self.event, guest.pk, self.t1.pk)  # même table : ne se compte pas deux fois
        seating.seat_guest(self.event, guest.pk, self.t2.pk)
        views = seating.board(self.event)["tables"]
        self.assertEqual((views[0].taken, views[1].taken), (0, 4))

    def test_empty_table_puts_the_guest_back_in_the_pool(self):
        guest = make_guest(self.event, "Roseline", table=self.t1)
        seating.seat_guest(self.event, guest.pk, "")
        guest.refresh_from_db()
        self.assertIsNone(guest.table_id)

    def test_unconfirmed_guests_cannot_be_seated(self):
        for status in ("pending", "maybe", "declined"):
            guest = make_guest(self.event, f"Invité {status}", status=status)
            with self.assertRaises(seating.SeatingError):
                seating.seat_guest(self.event, guest.pk, self.t1.pk)

    def test_tables_and_guests_of_another_event_are_refused(self):
        other = make_event(title="Autre")
        other_table = Table.objects.create(event=other, number=1)
        guest = make_guest(self.event, "Roseline")
        with self.assertRaises(seating.SeatingError):
            seating.seat_guest(self.event, guest.pk, other_table.pk)
        with self.assertRaises(seating.SeatingError):
            seating.seat_guest(self.event, make_guest(other, "Étranger").pk, self.t1.pk)
        for bad in ("", "x", None, 0, 99999):
            with self.assertRaises(seating.SeatingError):
                seating.seat_guest(self.event, bad, self.t1.pk)
        with self.assertRaises(seating.SeatingError):
            seating.seat_guest(self.event, guest.pk, "99999")


class TableManagementTests(TestCase):
    def setUp(self):
        self.event = make_event()

    def test_numbers_follow_each_other_and_never_move_when_a_table_is_deleted(self):
        first = seating.add_table(self.event)
        second = seating.add_table(self.event, "  Amis proches ")
        third = seating.add_table(self.event, capacity=8)
        self.assertEqual([t.number for t in (first, second, third)], [1, 2, 3])
        self.assertEqual((second.name, third.capacity), ("Amis proches", 8))
        seating.delete_table(self.event, second.pk)
        self.assertEqual(seating.add_table(self.event).number, 4)
        self.assertEqual(list(self.event.tables.values_list("number", flat=True)), [1, 3, 4])

    def test_twelve_tables_of_twelve_in_one_go(self):
        created = seating.add_tables(self.event, 12, 12)
        self.assertEqual(len(created), 12)
        self.assertEqual(list(self.event.tables.values_list("number", flat=True)), list(range(1, 13)))
        self.assertEqual(set(self.event.tables.values_list("capacity", flat=True)), {12})
        self.assertEqual(seating.board(self.event)["stats"]["seats"], 144)

    def test_limits(self):
        for bad in (0, 31, "x", "", None, -2):
            with self.assertRaises(seating.SeatingError):
                seating.add_table(self.event, capacity=bad)
        for bad in (0, 101, "x", None):
            with self.assertRaises(seating.SeatingError):
                seating.add_tables(self.event, bad, 12)
        seating.add_tables(self.event, 100, 2)
        with self.assertRaises(seating.SeatingError):
            seating.add_table(self.event)
        with self.assertRaises(seating.SeatingError):
            seating.add_tables(self.event, 1, 2)

    def test_edit_name_and_seats_but_not_below_the_people_already_seated(self):
        table = seating.add_table(self.event, capacity=6)
        make_guest(self.event, "Nadège", companions=3, table=table)
        seating.update_table(self.event, table.pk, "Famille", 8)
        table.refresh_from_db()
        self.assertEqual((table.name, table.capacity), ("Famille", 8))
        seating.update_table(self.event, table.pk, "Famille", 4)  # 4 personnes déjà : pile
        with self.assertRaises(seating.SeatingError):
            seating.update_table(self.event, table.pk, "Famille", 3)
        table.refresh_from_db()
        self.assertEqual(table.capacity, 4)

    def test_deleting_a_table_sends_its_guests_back_to_the_pool(self):
        table = seating.add_table(self.event)
        keep = seating.add_table(self.event)
        make_guest(self.event, "Roseline", companions=1, table=table)
        make_guest(self.event, "Nadège", table=keep)
        label, freed = seating.delete_table(self.event, table.pk)
        self.assertEqual((label, freed), ("Table 1", 1))
        data = seating.board(self.event)
        self.assertEqual([g.name for g in data["unseated"]], ["Roseline"])
        self.assertEqual([v.table.number for v in data["tables"]], [2])
        with self.assertRaises(seating.SeatingError):
            seating.delete_table(self.event, table.pk)

    def test_tables_of_another_event_cannot_be_changed(self):
        other = Table.objects.create(event=make_event(title="Autre"), number=1)
        with self.assertRaises(seating.SeatingError):
            seating.update_table(self.event, other.pk, "Piratage", 5)
        with self.assertRaises(seating.SeatingError):
            seating.delete_table(self.event, other.pk)
        other.refresh_from_db()
        self.assertEqual(other.name, "")


class AutoPlaceTests(TestCase):
    def setUp(self):
        self.event = make_event()

    def test_parties_stay_together_and_tables_fill_one_after_the_other(self):
        seating.add_tables(self.event, 3, 4)
        family = make_guest(self.event, "Famille", companions=3)  # 4 personnes : une table à elle
        trio = make_guest(self.event, "Trio", companions=2)
        pair = make_guest(self.event, "Couple", companions=1)
        solo = make_guest(self.event, "Seul")
        placed, left_out = seating.auto_place(self.event)
        self.assertEqual((placed, left_out), (4, []))
        for guest in (family, trio, pair, solo):
            guest.refresh_from_db()
        self.assertEqual(family.table.number, 1)
        self.assertEqual(trio.table.number, 2)
        self.assertEqual(solo.table.number, 2)  # la place qui reste à la table du trio
        self.assertEqual(pair.table.number, 3)
        for view in seating.board(self.event)["tables"]:
            self.assertLessEqual(view.taken, view.table.capacity)

    def test_already_seated_guests_do_not_move(self):
        seating.add_tables(self.event, 2, 6)
        seated = make_guest(self.event, "Déjà", table=self.event.tables.get(number=2))
        make_guest(self.event, "Nouveau")
        seating.auto_place(self.event)
        seated.refresh_from_db()
        self.assertEqual(seated.table.number, 2)

    def test_guests_without_room_are_reported_and_left_alone(self):
        seating.add_tables(self.event, 1, 3)
        make_guest(self.event, "Quatuor", companions=3)
        small = make_guest(self.event, "Petit", companions=1)
        placed, left_out = seating.auto_place(self.event)
        self.assertEqual(placed, 1)
        self.assertEqual([g.name for g in left_out], ["Quatuor"])
        small.refresh_from_db()
        self.assertEqual(small.table.number, 1)

    def test_only_confirmed_guests_are_placed_and_no_tables_means_nobody_is(self):
        make_guest(self.event, "Attente", status="pending")
        self.assertEqual(seating.auto_place(self.event)[0], 0)
        seating.add_tables(self.event, 1, 10)
        self.assertEqual(seating.auto_place(self.event)[0], 0)
        self.assertEqual(Guest.objects.filter(table__isnull=False).count(), 0)


class SeatingPagesTests(TestCase):
    def setUp(self):
        self.admin = make_user("a@x.ht", "admin")
        self.event = make_event()
        self.t1 = Table.objects.create(event=self.event, number=1, capacity=4, name="Table d'honneur")
        self.t2 = Table.objects.create(event=self.event, number=2, capacity=4)
        self.nadege = make_guest(self.event, "Nadège Louis", companions=1, table=self.t1)
        self.roseline = make_guest(self.event, "Roseline Augustin", companions=2)
        self.client.login(email="a@x.ht", password=PASSWORD)

    def url(self, name, *args):
        return reverse(f"dashboard:{name}", args=[self.event.pk, *args])

    def test_pages_are_for_the_team_only(self):
        for client_user in (None, make_user("g@x.ht", "guest")):
            self.client.logout()
            if client_user:
                self.client.login(email=client_user.email, password=PASSWORD)
            for name in ("seating_event", "seating_live", "seating_print"):
                self.assertIn(self.client.get(self.url(name)).status_code, (302, 403), name)
            self.assertIn(self.client.get(reverse("dashboard:seating_index")).status_code, (302, 403))
            for name, args, data in (
                ("seating_seat", (), {"guest": self.roseline.pk, "table": self.t2.pk}),
                ("seating_auto", (), {}),
                ("seating_table_add", (), {"capacity": 5}),
                ("seating_table_bulk", (), {"count": 3, "capacity": 5}),
                ("seating_table_update", (self.t1.pk,), {"name": "X", "capacity": 6}),
                ("seating_table_delete", (self.t1.pk,), {}),
            ):
                self.assertIn(self.client.post(self.url(name, *args), data).status_code, (302, 403), name)
        self.roseline.refresh_from_db()
        self.assertIsNone(self.roseline.table_id)
        self.assertEqual(self.event.tables.count(), 2)

    def test_index_and_event_pages(self):
        r = self.client.get(reverse("dashboard:seating_index"))
        self.assertContains(r, "Mariage de Sarah et Jean-Marc")
        self.assertContains(r, "1 sans table")
        r = self.client.get(self.url("seating_event"))
        self.assertContains(r, "Placer les invités")
        self.assertContains(r, "Table d&#x27;honneur")
        self.assertContains(r, "Roseline Augustin")
        self.assertContains(r, "2 / 4 places")
        self.assertContains(r, "Scène et piste de danse")
        self.assertContains(r, 'draggable="true"')
        self.assertContains(r, "Imprimer le plan")

    def test_sidebar_link_and_event_page_without_tables(self):
        self.assertContains(self.client.get(reverse("dashboard:home")), reverse("dashboard:seating_index"))
        self.event.tables.all().delete()
        r = self.client.get(self.url("seating_event"))
        self.assertContains(r, "Aucune table pour l")
        self.assertContains(r, 'id="bulk-form"')
        self.assertContains(r, 'value="12"')

    def test_seat_endpoint_returns_the_new_board(self):
        r = self.client.post(self.url("seating_seat"), {"guest": self.roseline.pk, "table": self.t2.pk}, HTTP_X_REQUESTED_WITH="fetch")
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertIn("Roseline Augustin est placé(e) à la Table 2", data["message"])
        self.assertIn("Roseline Augustin", data["html"])
        self.roseline.refresh_from_db()
        self.assertEqual(self.roseline.table_id, self.t2.pk)
        r = self.client.post(self.url("seating_seat"), {"guest": self.roseline.pk, "table": ""})
        self.assertIn("retiré(e)", r.json()["message"])

    def test_seat_endpoint_refuses_a_full_table_and_still_returns_the_board(self):
        r = self.client.post(self.url("seating_seat"), {"guest": self.roseline.pk, "table": self.t1.pk})  # 2 places libres, il en faut 3
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()["ok"])
        self.assertIn("n'a plus assez de places", r.json()["error"])
        self.assertIn("Nadège Louis", r.json()["html"])
        self.roseline.refresh_from_db()
        self.assertIsNone(self.roseline.table_id)

    def test_table_endpoints(self):
        r = self.client.post(self.url("seating_table_add"), {"name": "Enfants", "capacity": 6})
        self.assertIn("Table 3 · Enfants ajoutée", r.json()["message"])
        r = self.client.post(self.url("seating_table_update", self.t2.pk), {"name": "Amis", "capacity": 8})
        self.assertTrue(r.json()["ok"])
        r = self.client.post(self.url("seating_table_update", self.t1.pk), {"name": "X", "capacity": 1})
        self.assertEqual(r.status_code, 400)
        r = self.client.post(self.url("seating_table_delete", self.t1.pk))
        self.assertIn("1 invité retourne", r.json()["message"])
        self.nadege.refresh_from_db()
        self.assertIsNone(self.nadege.table_id)
        r = self.client.post(self.url("seating_table_bulk"), {"count": 4, "capacity": 10})
        self.assertIn("4 tables créées", r.json()["message"])
        r = self.client.post(self.url("seating_table_bulk"), {"count": "x", "capacity": 10})
        self.assertEqual(r.status_code, 400)

    def test_auto_endpoint(self):
        r = self.client.post(self.url("seating_auto"))
        self.assertIn("1 invité placé", r.json()["message"])
        self.roseline.refresh_from_db()
        self.assertEqual(self.roseline.table_id, self.t2.pk)  # 3 personnes : la table de 4 est la plus juste
        self.assertIn("Personne à placer", self.client.post(self.url("seating_auto")).json()["message"])

    def test_live_and_print_pages(self):
        r = self.client.get(self.url("seating_live"))
        self.assertTrue(r.json()["ok"])
        self.assertIn("Roseline Augustin", r.json()["html"])
        r = self.client.get(self.url("seating_print"))
        self.assertContains(r, "Nadège Louis")
        self.assertContains(r, "window.print()")
        self.assertContains(r, "Sans table : 1 invité")
        self.assertNotContains(r, "admin-dashboard")

    def test_seat_of_another_events_table_is_refused_through_the_page(self):
        other = Table.objects.create(event=make_event(title="Autre"), number=1)
        r = self.client.post(self.url("seating_seat"), {"guest": self.roseline.pk, "table": other.pk})
        self.assertEqual(r.status_code, 400)

    def test_page_exists_in_three_languages(self):
        for code, heading, free, stage in (
            ("fr", "Placer les invités", "libres", "Scène et piste de danse"),
            ("en", "Seat the guests", "free", "Stage and dance floor"),
            ("ht", "Plase envite yo", "lib", "Sèn ak pis dans"),
        ):
            r = self.client.get(self.url("seating_event") + f"?lang={code}")
            self.assertContains(r, heading, msg_prefix=code)
            self.assertContains(r, free, msg_prefix=code)
            self.assertContains(r, stage, msg_prefix=code)
            if code != "fr":
                for french in ("Placer les invités", "Scène et piste de danse", "Placement automatique", "Sans table"):
                    self.assertNotContains(r, french, msg_prefix=code)
        for code, word in (("en", "Open the seating plan"), ("ht", "Louvri plan tab yo")):
            self.assertContains(self.client.get(reverse("dashboard:seating_index") + f"?lang={code}"), word)


class TableOnTheTicketTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.table = Table.objects.create(event=self.event, number=7, name="Amis proches", capacity=10)
        self.guest = make_guest(self.event, "Guerline Pierre", companions=1, table=self.table)

    def ticket(self, guest=None, lang="fr"):
        guest = guest or self.guest
        return self.client.get(reverse("events:invitation_ticket", args=[guest.magic_token]) + f"?lang={lang}")

    def test_the_ticket_shows_the_table(self):
        self.assertContains(self.ticket(), "Table 7 · Amis proches")
        self.assertContains(self.ticket(lang="ht"), "Tab 7 · Amis proches")

    def test_no_table_line_when_the_guest_has_no_table(self):
        guest = make_guest(self.event, "Sans table")
        r = self.ticket(guest)
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "ticket-table")

    def test_the_entrance_screen_gives_the_table(self):
        admin = make_user("a@x.ht", "admin")
        outcome = checkin.scan(self.event, self.guest.entry_code, admin)
        data = checkin.describe(outcome)
        self.assertEqual(data["table"], "Table 7 · Amis proches")
        second = checkin.describe(checkin.scan(self.event, self.guest.entry_code, admin))
        self.assertEqual(second["table"], "Table 7 · Amis proches")  # QR déjà utilisé : on rappelle quand même la table
        walk_in = checkin.describe(checkin.add_walk_in(self.event, "Sur place", 0, "", admin))
        self.assertEqual(walk_in["table"], "")

    def test_the_team_scanning_the_link_sees_the_table(self):
        self.client.login(email=make_user("a@x.ht", "admin").email, password=PASSWORD)
        r = self.client.get(reverse("events:entry_code", args=[self.guest.entry_code]))
        self.assertContains(r, "Table 7 · Amis proches")
