"""Tests de bout en bout des règles métier critiques d'EventLead."""
from datetime import time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from ads.models import Ad
from events.models import Event, EventGroup, Guest
from gifts.models import Gift, GiftClaim
from gifts.services import GiftUnavailableError, ResponseLockedError, confirm_response
from payments.models import Payment

PASSWORD = "MotDePasse-Solide-42"


def make_user(email, role="guest", **extra):
    u = CustomUser(username=email, email=email, role=role, **extra)
    u.set_password(PASSWORD)
    u.save()
    return u


def make_event(**kw):
    defaults = dict(title="Mariage test", event_type="private", date=timezone.localdate() + timedelta(days=10),
                    time=time(15, 0), venue="Pétion-Ville", latitude=18.51, longitude=-72.28, max_guests=50,
                    allow_companions=True, max_companions=2)
    defaults.update(kw)
    return Event.objects.create(**defaults)


class GiftRulesTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.g1 = Guest.objects.create(event=self.event, name="Alice", email="a@x.ht")
        self.g2 = Guest.objects.create(event=self.event, name="Bruno", email="b@x.ht")
        self.unique = Gift.objects.create(event=self.event, name="Service à café", quantity=1)
        self.double = Gift.objects.create(event=self.event, name="Verres", quantity=2)

    def test_last_unit_cannot_be_taken_twice(self):
        confirm_response(self.g1.pk, "confirmed", 0, True, [self.unique.pk])
        with self.assertRaises(GiftUnavailableError):
            confirm_response(self.g2.pk, "confirmed", 0, True, [self.unique.pk, self.double.pk])
        # Transaction annulée : rien n'a été écrit pour Bruno
        self.g2.refresh_from_db()
        self.assertIsNone(self.g2.replied_at)
        self.assertEqual(self.g2.status, "pending")
        self.assertFalse(GiftClaim.objects.filter(guest=self.g2).exists())

    def test_quantity_greater_than_one(self):
        confirm_response(self.g1.pk, "confirmed", 0, True, [self.double.pk])
        confirm_response(self.g2.pk, "confirmed", 0, True, [self.double.pk])
        self.assertEqual(self.double.claims.count(), 2)
        self.assertFalse(self.double.is_available)

    def test_confirmed_response_is_final(self):
        confirm_response(self.g1.pk, "confirmed", 1, True, [self.unique.pk])
        with self.assertRaises(ResponseLockedError):
            confirm_response(self.g1.pk, "declined", 0, None, [])
        self.assertEqual(GiftClaim.objects.filter(guest=self.g1).count(), 1)

    def test_no_gift_claim_when_declining(self):
        confirm_response(self.g1.pk, "declined", 2, True, [self.unique.pk])
        self.g1.refresh_from_db()
        self.assertEqual(self.g1.companions, 0)
        self.assertFalse(GiftClaim.objects.exists())

    def test_admin_cannot_delete_claimed_gift(self):
        confirm_response(self.g1.pk, "confirmed", 0, True, [self.unique.pk])
        admin = make_user("admin@x.ht", role="admin")
        self.client.force_login(admin)
        self.client.post(reverse("dashboard:gift_delete", args=[self.unique.pk]))
        self.assertTrue(Gift.objects.filter(pk=self.unique.pk).exists())
        self.client.post(reverse("dashboard:gift_delete", args=[self.double.pk]))
        self.assertFalse(Gift.objects.filter(pk=self.double.pk).exists())

    def test_no_guest_side_route_to_remove_a_claim(self):
        from django.urls import get_resolver

        routes = [str(p.pattern) for p in get_resolver().url_patterns]
        invitation_routes = [r for r in self._all_routes(get_resolver()) if r.startswith("invitation/")]
        self.assertTrue(invitation_routes, routes)
        for route in invitation_routes:
            self.assertNotIn("supprimer", route)
            self.assertNotIn("annuler", route)

    def _all_routes(self, resolver, prefix=""):
        out = []
        for p in resolver.url_patterns:
            if hasattr(p, "url_patterns"):
                out += self._all_routes(p, prefix + str(p.pattern))
            else:
                out.append(prefix + str(p.pattern))
        return out

    def test_guest_never_sees_who_took_a_gift(self):
        confirm_response(self.g1.pk, "confirmed", 0, True, [self.unique.pk])
        url = reverse("events:invitation_gift_availability", args=[self.g2.magic_token])
        body = self.client.get(url).content.decode()
        self.assertNotIn("Alice", body)


class InvitationFlowTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.guest = Guest.objects.create(event=self.event, name="Carla", phone="+509 3712 3456")
        self.gift = Gift.objects.create(event=self.event, name="Lampe", icon_name="bi-lamp")
        self.ad = Ad.objects.create(title="Pub", message="m", sponsor_link="https://example.com")
        self.token = self.guest.magic_token

    def url(self, name, *extra):
        return reverse(f"events:{name}", args=[self.token, *extra])

    def test_guest_never_asked_to_log_in(self):
        """Le lien personnel suffit : aucune étape du parcours ne renvoie vers la connexion."""
        login = reverse("accounts:login")
        for name in ("invitation", "invitation_gift_question", "invitation_gift_list", "invitation_recap"):
            r = self.client.get(self.url(name))
            self.assertNotIn(login, r.get("Location", ""), name)
            self.assertIn(r.status_code, (200, 302), name)
        self.assertEqual(self.client.get(self.url("invitation")).status_code, 200)
        self.assertEqual(self.client.get(self.url("invitation_ad", self.ad.pk)).status_code, 200)

    def test_full_flow_with_gift(self):
        r = self.client.get(self.url("invitation"))
        self.assertContains(r, "Serez-vous")
        r = self.client.post(self.url("invitation"), {"status": "confirmed", "companions": 2})
        self.assertRedirects(r, self.url("invitation_gift_question"))
        r = self.client.post(self.url("invitation_gift_question"), {"wants_gift": "yes"})
        self.assertRedirects(r, self.url("invitation_gift_list"))
        self.assertContains(self.client.get(self.url("invitation_gift_list")), "définitive")
        r = self.client.post(self.url("invitation_gift_list"), {"gifts": [self.gift.pk]})
        self.assertRedirects(r, self.url("invitation_recap"))
        self.assertContains(self.client.get(self.url("invitation_recap")), "Confirmer définitivement")
        r = self.client.post(self.url("invitation_recap"))
        self.assertRedirects(r, self.url("invitation_done"), fetch_redirect_response=False)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.status, "confirmed")
        self.assertEqual(self.guest.companions, 2)
        self.assertTrue(self.guest.wants_gift)
        self.assertIsNotNone(self.guest.replied_at)
        self.assertEqual(self.gift.claims.get().guest, self.guest)
        # Confirmation -> redirection automatique vers la publicité -> accueil
        r = self.client.get(self.url("invitation_done"))
        self.assertRedirects(r, self.url("invitation_ad", self.ad.pk), fetch_redirect_response=False)
        r = self.client.get(self.url("invitation_ad", self.ad.pk))
        self.assertContains(r, reverse("core:landing") + "#affiche")
        self.assertContains(r, "Merci Carla")
        self.ad.refresh_from_db()
        self.assertEqual(self.ad.views, 1)
        self.client.get(reverse("ads:click", args=[self.ad.pk]))
        self.ad.refresh_from_db()
        self.assertEqual(self.ad.clicks, 1)
        # Retour sur le lien : réponse figée, pas de formulaire
        r = self.client.get(self.url("invitation"))
        self.assertContains(r, "Cette réponse est définitive")
        self.assertNotContains(r, 'name="status"')

    def test_without_ads_done_page_leads_to_home(self):
        Ad.objects.all().delete()
        self.client.post(self.url("invitation"), {"status": "declined"})
        self.client.post(self.url("invitation_recap"))
        r = self.client.get(self.url("invitation_done"))
        self.assertContains(r, reverse("core:landing") + "#affiche")

    def test_ads_chain_ends_on_home(self):
        second = Ad.objects.create(title="Pub 2", message="m", sponsor_link="https://example.com/2", order=2)
        self.client.post(self.url("invitation"), {"status": "declined"})
        self.client.post(self.url("invitation_recap"))
        r = self.client.get(self.url("invitation_ad", self.ad.pk))
        self.assertContains(r, self.url("invitation_ad", second.pk))
        r = self.client.get(self.url("invitation_ad", second.pk))
        self.assertContains(r, reverse("core:landing") + "#affiche")

    def test_gift_steps_skipped_when_declining(self):
        r = self.client.post(self.url("invitation"), {"status": "declined"})
        self.assertRedirects(r, self.url("invitation_recap"))
        self.client.post(self.url("invitation_recap"))
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.status, "declined")
        self.assertIsNone(self.guest.wants_gift)

    def test_gift_taken_meanwhile_sends_back_to_list(self):
        other = Guest.objects.create(event=self.event, name="Dan")
        self.client.post(self.url("invitation"), {"status": "confirmed", "companions": 0})
        self.client.post(self.url("invitation_gift_question"), {"wants_gift": "yes"})
        self.client.post(self.url("invitation_gift_list"), {"gifts": [self.gift.pk]})
        confirm_response(other.pk, "confirmed", 0, True, [self.gift.pk])
        r = self.client.post(self.url("invitation_recap"))
        self.assertRedirects(r, self.url("invitation_gift_list"))
        self.guest.refresh_from_db()
        self.assertIsNone(self.guest.replied_at)

    def test_companions_limit(self):
        r = self.client.post(self.url("invitation"), {"status": "confirmed", "companions": 5})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Maximum 2")


class HomeParadeTests(TestCase):
    """Accueil : défilé des publications, événements publics et billets."""

    def setUp(self):
        self.free = make_event(title="Conférence ouverte", event_type="public", status="active")
        self.paid = make_event(title="Gala payant", event_type="public", status="active", price_htg=Decimal("3500"))
        self.private = make_event(title="Mariage secret")
        self.ad = Ad.objects.create(title="Pâtisserie Test", message="Gâteaux", sponsor_link="https://example.com")
        Ad.objects.create(title="Pub inactive", message="x", sponsor_link="https://example.com", is_active=False)

    def test_parade_mixes_ads_events_and_tickets(self):
        r = self.client.get(reverse("core:landing"))
        self.assertContains(r, 'id="affiche"')
        self.assertContains(r, "Pâtisserie Test")
        self.assertContains(r, "Conférence ouverte")
        self.assertContains(r, "p-card ticket")
        self.assertContains(r, reverse("payments:checkout", args=[self.paid.pk]))
        self.assertNotContains(r, "Mariage secret")
        self.assertNotContains(r, "Pub inactive")
        kinds = [k for k, _ in r.context["parade"]]
        self.assertTrue({"ad", "event", "ticket"} <= set(kinds))

    def test_public_landing_explains_how_it_works_without_invented_figures(self):
        r = self.client.get(reverse("core:landing"))
        self.assertContains(r, 'id="comment-ca-marche"')
        self.assertContains(r, "sans compte ni application")
        self.assertNotContains(r, "de satisfaction")
        self.assertNotContains(r, "de réponses visées")
        self.assertNotContains(r, "hero-invite")

    def test_footer_is_the_original_four_column_one(self):
        r = self.client.get(reverse("core:landing"))
        self.assertContains(r, "Espace pro")
        self.assertContains(r, "La plateforme élégante pour organiser vos mariages")
        self.assertNotContains(r, 'class="sign"')

    def test_parade_hidden_when_nothing_to_show(self):
        Event.objects.all().delete()
        Ad.objects.all().delete()
        self.assertNotContains(self.client.get(reverse("core:landing")), 'id="affiche"')

    def test_logged_in_visitor_gets_welcome_and_parade(self):
        make_user("g@x.ht")
        self.client.login(email="g@x.ht", password=PASSWORD)
        r = self.client.get(reverse("core:landing"))
        self.assertContains(r, "Bonjour")
        self.assertContains(r, 'id="affiche"')

    def test_login_redirects_to_home(self):
        make_user("g@x.ht")
        r = self.client.post(reverse("accounts:login"), {"email": "g@x.ht", "password": PASSWORD})
        self.assertRedirects(r, reverse("core:landing"), fetch_redirect_response=False)

    def test_login_redirects_by_role(self):
        make_user("a@x.ht", role="admin")
        make_user("v@x.ht", role="organizer", is_vip=True)
        make_user("o@x.ht", role="organizer")
        for email, target in [("a@x.ht", reverse("dashboard:home")), ("v@x.ht", reverse("core:landing")),
                              ("o@x.ht", reverse("payments:vip"))]:
            self.client.logout()
            r = self.client.post(reverse("accounts:login"), {"email": email, "password": PASSWORD})
            self.assertRedirects(r, target, fetch_redirect_response=False)


class AccessRulesTests(TestCase):
    def setUp(self):
        self.public = make_event(title="Gala public", event_type="public")
        self.private = make_event(title="Mariage privé")
        self.other_private = make_event(title="Autre privé")
        self.vip = make_user("vip@x.ht", role="organizer", is_vip=True)
        Guest.objects.create(event=self.private, name="VIP", user=self.vip)

    def test_landing_lists_public_events_only(self):
        r = self.client.get(reverse("core:landing"))
        self.assertContains(r, "Gala public")
        self.assertNotContains(r, "Mariage privé")

    def test_anonymous_cannot_see_private_event(self):
        self.assertEqual(self.client.get(reverse("events:public_detail", args=[self.private.pk])).status_code, 404)

    def test_unpaid_organizer_is_blocked(self):
        make_user("org@x.ht", role="organizer")
        self.client.login(email="org@x.ht", password=PASSWORD)
        self.assertRedirects(self.client.get(reverse("events:organizer_portal")), reverse("payments:vip"))

    def test_vip_sees_public_and_invited_private_only(self):
        self.client.force_login(self.vip)
        r = self.client.get(reverse("events:organizer_portal"))
        self.assertContains(r, "Gala public")
        self.assertContains(r, "Mariage privé")
        self.assertNotContains(r, "Autre privé")
        self.assertNotContains(r, reverse("dashboard:event_create"))

    def test_organizer_cannot_reach_admin_dashboard(self):
        self.client.force_login(self.vip)
        self.assertEqual(self.client.get(reverse("dashboard:event_create")).status_code, 403)

    def test_login_redirects_by_role(self):
        make_user("adm@x.ht", role="admin")
        r = self.client.post(reverse("accounts:login"), {"email": "adm@x.ht", "password": PASSWORD})
        self.assertRedirects(r, reverse("dashboard:home"))


class PaymentTests(TestCase):
    def setUp(self):
        self.user = make_user("new@x.ht", role="organizer")
        self.client.force_login(self.user)

    def test_vip_payment_with_moncash(self):
        r = self.client.post(reverse("payments:vip"), {"method": "moncash", "phone": "3712 3456", "otp": "123456"})
        payment = Payment.objects.get()
        self.assertRedirects(r, reverse("payments:success", args=[payment.reference]))
        self.assertTrue(payment.reference.startswith("MC-"))
        self.assertEqual(payment.status, "success")
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_vip)
        self.assertEqual(self.client.get(reverse("events:organizer_portal")).status_code, 200)

    def test_wrong_otp_records_failed_payment(self):
        self.client.post(reverse("payments:vip"), {"method": "moncash", "phone": "3712 3456", "otp": "000000"})
        self.assertEqual(Payment.objects.get().status, "failed")
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_vip)

    def test_ticket_with_card(self):
        event = make_event(event_type="public", price_htg=Decimal("1000"))
        exp = (timezone.localdate() + timedelta(days=400)).strftime("%m/%y")
        r = self.client.post(reverse("payments:checkout", args=[event.pk]), {
            "method": "stripe", "quantity": 3, "card_number": "4242 4242 4242 4242",
            "card_expiry": exp, "card_cvc": "123", "card_name": "Test",
        })
        p = Payment.objects.get()
        self.assertRedirects(r, reverse("payments:success", args=[p.reference]))
        self.assertEqual(p.amount_htg, Decimal("3000"))
        self.assertEqual(p.payer_detail, "Carte **** 4242")

    def test_history_is_admin_only(self):
        self.assertEqual(self.client.get(reverse("dashboard:payment_history")).status_code, 403)


class SmokeTests(TestCase):
    """Chaque page principale s'affiche pour le bon rôle."""

    def setUp(self):
        from django.core.management import call_command

        call_command("seed_demo", stdout=open("/dev/null", "w"))

    def test_public_pages(self):
        event = Event.objects.public_active().first()
        for url in [reverse("core:landing"), reverse("events:explore"), reverse("payments:ticketing"),
                    reverse("accounts:login"), reverse("accounts:register"), reverse("accounts:register_organizer"),
                    reverse("ads:list"), reverse("events:public_detail", args=[event.pk])]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_admin_pages(self):
        self.client.login(email="admin@eventlead.ht", password="EventLead2026!")
        event = Event.objects.get(title__startswith="Mariage")
        guest = event.guests.first()
        gift = event.gifts.first()
        ad = Ad.objects.first()
        urls = [
            reverse("dashboard:home"), reverse("dashboard:event_list"), reverse("dashboard:event_create"),
            reverse("dashboard:event_detail", args=[event.pk]), reverse("dashboard:event_live", args=[event.pk]),
            reverse("dashboard:event_edit", args=[event.pk]), reverse("dashboard:guest_list"),
            reverse("dashboard:guest_list") + f"?event={event.pk}", reverse("dashboard:guest_create"),
            reverse("dashboard:guest_edit", args=[guest.pk]), reverse("dashboard:gift_list"),
            reverse("dashboard:gift_create"), reverse("dashboard:gift_edit", args=[gift.pk]),
            reverse("dashboard:ad_list"), reverse("dashboard:ad_create"), reverse("dashboard:ad_edit", args=[ad.pk]),
            reverse("dashboard:payment_history"), reverse("dashboard:inbox"),
            reverse("dashboard:guest_export_csv"), reverse("dashboard:gift_export_csv"),
            reverse("dashboard:guest_export_pdf") + f"?event={event.pk}", "/django-admin/",
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_vip_pages(self):
        self.client.login(email="organisateur@eventlead.ht", password="EventLead2026!")
        r = self.client.get(reverse("events:organizer_portal"))
        self.assertContains(r, "Évaluer")
        past = Event.objects.get(title__startswith="Anniversaire")
        self.assertEqual(self.client.get(reverse("events:evaluate", args=[past.pk])).status_code, 200)
        self.client.post(reverse("events:evaluate", args=[past.pk]), {"stars": 5, "comment": "Superbe"})
        self.assertEqual(past.evaluations.count(), 1)

    def test_guest_pages(self):
        self.client.login(email="invite@eventlead.ht", password="EventLead2026!")
        self.assertContains(self.client.get(reverse("accounts:guest_space")), "Mariage")
        event = Event.objects.filter(price_htg__gt=0).first()
        self.assertEqual(self.client.get(reverse("payments:checkout", args=[event.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("payments:vip")).status_code, 200)


class EventGroupTests(TestCase):
    """Groupes d'événements : gestion par l'administrateur et présentation publique."""

    def setUp(self):
        self.admin = make_user("adm@x.ht", role="admin")
        self.day1 = make_event(title="Ouverture du festival", event_type="public", status="active")
        self.day2 = make_event(title="Clôture du festival", event_type="public", status="active",
                               date=timezone.localdate() + timedelta(days=11), price_htg=Decimal("2000"))
        self.alone = make_event(title="Conférence seule", event_type="public", status="active",
                                date=timezone.localdate() + timedelta(days=20))
        self.secret = make_event(title="Dîner privé du festival")

    def make_group(self, *events, title="Festival test"):
        group = EventGroup.objects.create(title=title, description="Deux jours de fête")
        Event.objects.filter(pk__in=[e.pk for e in events]).update(group=group)
        return group

    def post_group(self, url, events, title="Festival test"):
        self.client.force_login(self.admin)
        return self.client.post(url, {"title": title, "description": "x", "events": [e.pk for e in events]})

    # ---- tableau de bord
    def test_admin_creates_group_and_attaches_events(self):
        r = self.post_group(reverse("dashboard:group_create"), [self.day1, self.day2])
        self.assertRedirects(r, reverse("dashboard:group_list"))
        group = EventGroup.objects.get(title="Festival test")
        self.assertEqual(set(group.events.all()), {self.day1, self.day2})

    def test_admin_detaches_and_moves_events(self):
        group = self.make_group(self.day1, self.day2)
        self.post_group(reverse("dashboard:group_edit", args=[group.pk]), [self.day1])
        self.day2.refresh_from_db()
        self.assertIsNone(self.day2.group)
        other = EventGroup.objects.create(title="Autre groupe")
        self.post_group(reverse("dashboard:group_edit", args=[other.pk]), [self.day1], title="Autre groupe")
        self.day1.refresh_from_db()
        self.assertEqual(self.day1.group, other)

    def test_deleting_group_keeps_its_events(self):
        group = self.make_group(self.day1, self.day2)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("dashboard:group_delete", args=[group.pk])), "ne sont pas supprimés")
        self.client.post(reverse("dashboard:group_delete", args=[group.pk]))
        self.assertFalse(EventGroup.objects.exists())
        self.day1.refresh_from_db()
        self.assertIsNone(self.day1.group)
        self.assertTrue(Event.objects.filter(pk=self.day2.pk).exists())

    def test_event_form_can_set_the_group(self):
        group = EventGroup.objects.create(title="Mariage")
        self.client.force_login(self.admin)
        r = self.client.post(reverse("dashboard:event_edit", args=[self.secret.pk]), {
            "title": self.secret.title, "group": group.pk, "event_type": "private", "status": "active",
            "date": self.secret.date.isoformat(), "time": "15:00", "venue": self.secret.venue,
            "latitude": 18.51, "longitude": -72.28, "max_guests": 50, "max_companions": 0, "evaluation_delay_days": 3,
        })
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        self.secret.refresh_from_db()
        self.assertEqual(self.secret.group, group)

    def test_group_pages_are_admin_only_and_render(self):
        group = self.make_group(self.day1)
        self.client.force_login(make_user("vip@x.ht", role="organizer", is_vip=True))
        self.assertEqual(self.client.get(reverse("dashboard:group_list")).status_code, 403)
        self.client.force_login(self.admin)
        for url in (reverse("dashboard:group_list"), reverse("dashboard:group_create"),
                    reverse("dashboard:group_edit", args=[group.pk]), reverse("dashboard:event_list")):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    # ---- pages publiques
    def test_group_is_one_card_with_its_public_events_only(self):
        self.make_group(self.day1, self.day2, self.secret)
        for url in (reverse("core:landing"), reverse("events:explore")):
            r = self.client.get(url)
            self.assertContains(r, 'class="event-arch group-arch"', count=1, msg_prefix=url)
            self.assertContains(r, "Ouverture du festival")
            self.assertContains(r, "Clôture du festival")
            self.assertContains(r, "Conférence seule")
            self.assertNotContains(r, "Dîner privé du festival")
        cards = self.client.get(reverse("events:explore")).context["cards"]
        self.assertEqual([c["kind"] for c in cards], ["group", "event"])
        self.assertEqual(cards[0]["count"], 2)

    def test_group_without_public_event_is_hidden(self):
        self.make_group(self.secret, title="Groupe privé")
        r = self.client.get(reverse("events:explore"))
        self.assertNotContains(r, "Groupe privé")
        self.assertNotContains(r, "group-arch")

    def test_parade_shows_a_group_as_one_card(self):
        self.make_group(self.day1, self.day2)
        from core.views import build_parade

        kinds = [k for k, _ in build_parade(minimum=1)]
        self.assertEqual(kinds.count("group"), 1)
        self.assertEqual(kinds.count("event"), 1)  # la conférence seule
        self.assertIn("ticket", kinds)  # le billet de la clôture reste achetable
        self.assertContains(self.client.get(reverse("core:landing")), "Festival test")

    def test_event_page_lists_the_other_events_of_its_group(self):
        self.make_group(self.day1, self.day2, self.secret)
        r = self.client.get(reverse("events:public_detail", args=[self.day1.pk]))
        self.assertContains(r, "Dans le même groupe")
        self.assertContains(r, "Clôture du festival")
        self.assertNotContains(r, "Dîner privé du festival")

    def test_invitation_flow_is_unchanged_for_grouped_events(self):
        self.make_group(self.secret, self.day1)
        guest = Guest.objects.create(event=self.secret, name="Carla", phone="+509 3712 3456")
        r = self.client.get(reverse("events:invitation", args=[guest.magic_token]))
        self.assertContains(r, "Serez-vous")
        self.assertContains(r, "Dîner privé du festival")
