"""Tests de bout en bout des règles métier critiques d'EventLead."""
import os
from datetime import time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from core.models import HelpRequest
from ads.models import Ad
from events.models import Event, EventCategory, Guest
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


class EventCategoryTests(TestCase):
    def setUp(self):
        self.gala_cat = EventCategory.objects.create(name="Gala", icon_name="bi-stars", order=1)
        self.concert_cat = EventCategory.objects.create(name="Concert", icon_name="bi-music-note-beamed", order=2)
        self.empty_cat = EventCategory.objects.create(name="Baptême", icon_name="bi-droplet", order=3)
        self.gala = make_event(title="Grand gala", event_type="public", category=self.gala_cat)
        self.concert = make_event(title="Concert kompa", event_type="public", category=self.concert_cat)
        self.plain = make_event(title="Sans catégorie", event_type="public")
        self.private = make_event(title="Mariage privé", category=self.empty_cat)
        self.admin = make_user("adm@x.ht", role="admin")

    def test_slug_is_generated_and_unique(self):
        self.assertEqual(self.empty_cat.slug, "bapteme")
        twin = EventCategory(name="Gala!")
        twin.save()
        self.assertEqual(twin.slug, "gala-2")

    def test_landing_filters_by_category(self):
        r = self.client.get(reverse("core:landing"), {"categorie": "concert"})
        # Le filtre porte sur la section « événements publics » (le défilé « À l'affiche » reste complet).
        section = r.content.decode().split('id="evenements"')[1].split('id="services"')[0]
        self.assertIn("Concert kompa", section)
        self.assertNotIn("Grand gala", section)
        self.assertNotIn("Sans catégorie", section)
        self.assertIn('class="cat-chip active"', section)

    def test_explore_filters_by_category(self):
        r = self.client.get(reverse("events:explore"), {"categorie": "gala"})
        self.assertContains(r, "Grand gala")
        self.assertNotContains(r, "Concert kompa")

    def test_unknown_category_shows_everything(self):
        r = self.client.get(reverse("events:explore"), {"categorie": "n-importe-quoi"})
        for title in ("Grand gala", "Concert kompa", "Sans catégorie"):
            self.assertContains(r, title)

    def test_filter_row_lists_only_categories_with_public_events(self):
        r = self.client.get(reverse("events:explore"))
        self.assertContains(r, "?categorie=gala#evenements")
        self.assertContains(r, "?categorie=concert#evenements")
        self.assertNotContains(r, "?categorie=bapteme")

    def test_private_event_category_is_not_exposed(self):
        r = self.client.get(reverse("events:explore"), {"categorie": "bapteme"})
        self.assertNotContains(r, "Mariage privé")
        self.assertNotContains(r, "Baptême")

    def test_cards_show_category_badge(self):
        r = self.client.get(reverse("events:explore"))
        self.assertContains(r, 'class="cat-badge"', count=2)

    def test_detail_shows_category(self):
        r = self.client.get(reverse("events:public_detail", args=[self.gala.pk]))
        self.assertContains(r, "Événement public &middot; Gala")

    def test_dashboard_category_pages_are_admin_only(self):
        urls = [reverse("dashboard:category_list"), reverse("dashboard:category_create"),
                reverse("dashboard:category_edit", args=[self.gala_cat.pk]),
                reverse("dashboard:category_delete", args=[self.gala_cat.pk])]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302, url)
        self.client.force_login(make_user("vip2@x.ht", role="organizer", is_vip=True))
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403, url)
        self.client.force_login(self.admin)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_dashboard_lists_categories_in_display_order(self):
        self.client.force_login(self.admin)
        names = [c.name for c in self.client.get(reverse("dashboard:category_list")).context["categories"]]
        self.assertEqual(names, ["Gala", "Concert", "Baptême"])

    def test_admin_can_create_edit_and_delete_a_category(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("dashboard:category_create"),
                             {"name": "Fête de quartier", "icon_name": "bi-balloon", "order": 9})
        self.assertRedirects(r, reverse("dashboard:category_list"))
        cat = EventCategory.objects.get(name="Fête de quartier")
        self.assertEqual(cat.slug, "fete-de-quartier")
        self.client.post(reverse("dashboard:category_edit", args=[cat.pk]),
                         {"name": "Fête de rue", "icon_name": "bi-cup-straw", "order": 4})
        cat.refresh_from_db()
        self.assertEqual((cat.name, cat.icon_name, cat.order, cat.slug), ("Fête de rue", "bi-cup-straw", 4, "fete-de-quartier"))
        self.client.post(reverse("dashboard:category_delete", args=[cat.pk]))
        self.assertFalse(EventCategory.objects.filter(pk=cat.pk).exists())

    def test_category_name_must_be_unique_ignoring_case(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("dashboard:category_create"),
                             {"name": "gala", "icon_name": "bi-stars", "order": 1})
        self.assertContains(r, "Une catégorie porte déjà ce nom.")
        self.assertEqual(EventCategory.objects.filter(name__iexact="gala").count(), 1)

    def test_deleting_a_category_keeps_its_events(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("dashboard:category_delete", args=[self.gala_cat.pk]))
        self.gala.refresh_from_db()
        self.assertIsNone(self.gala.category)
        self.assertTrue(Event.objects.filter(pk=self.gala.pk).exists())

    def test_event_form_sets_the_category(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("dashboard:event_edit", args=[self.plain.pk]), {
            "title": "Sans catégorie", "event_type": "public", "status": "active",
            "date": self.plain.date.isoformat(), "time": "15:00", "venue": "Pétion-Ville",
            "max_guests": 50, "max_companions": 0, "evaluation_delay_days": 3,
            "price_htg": 0, "category": self.concert_cat.pk,
        })
        self.assertRedirects(r, reverse("dashboard:event_detail", args=[self.plain.pk]))
        self.plain.refresh_from_db()
        self.assertEqual(self.plain.category, self.concert_cat)

    def test_dashboard_event_list_filters_by_category(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("dashboard:event_list"), {"categorie": "gala"})
        self.assertContains(r, "Grand gala")
        self.assertNotContains(r, "Concert kompa")


class HelpSpaceTests(TestCase):
    def setUp(self):
        self.admin = make_user("adm@x.ht", role="admin")

    def post_help(self, **extra):
        data = {"name": "Marie", "contact": "marie@example.com", "topic": "payment", "message": "Le code ne vient pas.", "website": ""}
        data.update(extra)
        return self.client.post(reverse("core:help"), data)

    # -- page publique -------------------------------------------------------
    def test_help_page_has_three_profiles_and_key_answers(self):
        r = self.client.get(reverse("core:help"))
        self.assertEqual(r.status_code, 200)
        for title in ("Invité ou visiteur", "Organisateur VIP", "Équipe EventLead"):
            self.assertContains(r, title)
        for slug in ("invite-sans-compte", "invite-cadeau", "paiement-moncash", "paiement-natcash", "vip-devenir"):
            self.assertContains(r, f'id="faq-{slug}"')
        self.assertContains(r, "Dois-je créer un compte")

    def test_help_page_does_not_ask_to_log_in(self):
        self.assertEqual(self.client.get(reverse("core:help")).status_code, 200)

    def test_whatsapp_floating_button_uses_the_contact_number(self):
        from django.conf import settings

        for url in (reverse("core:landing"), reverse("core:help"), reverse("events:explore")):
            r = self.client.get(url)
            self.assertContains(r, 'class="fab-help"', msg_prefix=url)
            self.assertContains(r, f"https://wa.me/{settings.CONTACT_WHATSAPP}?text=", msg_prefix=url)

    def test_no_floating_button_in_dashboard_or_invitation(self):
        self.client.force_login(self.admin)
        self.assertNotContains(self.client.get(reverse("dashboard:home")), 'class="fab-help"')
        self.client.logout()
        guest = Guest.objects.create(event=make_event(), name="Carla", phone="+509 3712 3456")
        r = self.client.get(reverse("events:invitation", args=[guest.magic_token]))
        self.assertNotContains(r, 'class="fab-help"')
        self.assertContains(r, "Écrire sur WhatsApp")

    # -- formulaire ----------------------------------------------------------
    def test_help_request_is_saved_as_new(self):
        r = self.post_help()
        self.assertRedirects(r, reverse("core:help") + "?envoye=1#demande", fetch_redirect_response=False)
        req = HelpRequest.objects.get()
        self.assertEqual((req.name, req.contact, req.topic, req.status), ("Marie", "marie@example.com", "payment", "new"))
        self.assertContains(self.client.get(reverse("core:help"), {"envoye": "1"}), "votre demande est bien arrivée")

    def test_help_request_accepts_a_phone_number(self):
        self.post_help(contact="+509 3712 3456")
        self.assertEqual(HelpRequest.objects.get().whatsapp_number, "50937123456")

    def test_help_request_rejects_a_bad_contact_or_empty_message(self):
        for bad in ({"contact": "pas-un-contact"}, {"contact": "nom@"}, {"message": ""}, {"name": ""}):
            r = self.post_help(**bad)
            self.assertEqual(r.status_code, 200, bad)
        self.assertEqual(HelpRequest.objects.count(), 0)

    def test_help_form_honeypot_saves_nothing(self):
        self.post_help(website="http://spam.example")
        self.assertEqual(HelpRequest.objects.count(), 0)

    def test_help_form_prefills_topic_and_logged_in_user(self):
        r = self.client.get(reverse("core:help"), {"sujet": "gift"})
        self.assertEqual(r.context["form"].initial["topic"], "gift")
        self.client.force_login(self.admin)
        r = self.client.get(reverse("core:help"), {"sujet": "n-importe-quoi"})
        self.assertEqual(r.context["form"].initial["contact"], "adm@x.ht")
        self.assertNotIn("topic", r.context["form"].initial)

    def test_whatsapp_number_normalisation(self):
        make = lambda contact: HelpRequest(name="x", contact=contact, message="m")
        self.assertEqual(make("3712 3456").whatsapp_number, "50937123456")
        self.assertEqual(make("+1 305 555 0100").whatsapp_number, "13055550100")
        self.assertEqual(make("a@b.ht").whatsapp_number, "")
        self.assertEqual(make("12345").whatsapp_number, "")

    # -- aides dans le parcours ----------------------------------------------
    def test_guest_flow_has_quiet_hints(self):
        event = make_event()
        Gift.objects.create(event=event, name="Lampe", icon_name="bi-lamp")
        guest = Guest.objects.create(event=event, name="Carla", phone="+509 3712 3456")
        url = lambda name: reverse(f"events:{name}", args=[guest.magic_token])
        self.assertContains(self.client.get(url("invitation")), "Pas de compte à créer ?")
        self.client.post(url("invitation"), {"status": "confirmed", "companions": 0})
        self.client.post(url("invitation_gift_question"), {"wants_gift": "yes"})
        self.assertContains(self.client.get(url("invitation_gift_list")), "Un cadeau a disparu de la liste ?")
        self.client.post(url("invitation_gift_list"), {"gifts": [event.gifts.first().pk]})
        r = self.client.get(url("invitation_recap"))
        self.assertContains(r, "Une erreur dans ma réponse ?")
        self.assertContains(r, "?sujet=invitation#demande")

    def test_every_hint_target_exists_in_the_faq(self):
        from core.help import HELP_PROFILES

        slugs = {slug for profile in HELP_PROFILES for slug, _, _ in profile["questions"]}
        for slug in ("invite-sans-compte", "invite-cadeau-disparu", "invite-modifier"):
            self.assertIn(slug, slugs)

    def test_payment_modal_has_sms_hint_and_help_link(self):
        guest_user = make_user("g@x.ht")
        event = make_event(event_type="public", price_htg=Decimal("1000"))
        self.client.force_login(guest_user)
        r = self.client.get(reverse("payments:checkout", args=[event.pk]))
        self.assertContains(r, "code de confirmation à 6 chiffres")
        self.assertContains(r, "?sujet=payment#demande")

    # -- tableau de bord -----------------------------------------------------
    def test_dashboard_help_pages_are_admin_only(self):
        req = HelpRequest.objects.create(name="Marie", contact="m@x.ht", message="Aide")
        urls = [reverse("dashboard:help_list"), reverse("dashboard:help_export_csv")]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302, url)
        self.client.force_login(make_user("vip3@x.ht", role="organizer", is_vip=True))
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403, url)
        self.assertEqual(self.client.post(reverse("dashboard:help_set_status", args=[req.pk]), {"status": "resolved"}).status_code, 403)
        req.refresh_from_db()
        self.assertEqual(req.status, "new")
        self.client.force_login(self.admin)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_admin_changes_status_and_filter_is_kept(self):
        req = HelpRequest.objects.create(name="Marie", contact="m@x.ht", message="Aide")
        self.client.force_login(self.admin)
        url = reverse("dashboard:help_set_status", args=[req.pk])
        r = self.client.post(url, {"status": "in_progress", "filter": "new"})
        self.assertRedirects(r, reverse("dashboard:help_list") + "?statut=new")
        req.refresh_from_db()
        self.assertEqual(req.status, "in_progress")
        self.client.post(url, {"status": "pas-un-statut"})
        req.refresh_from_db()
        self.assertEqual(req.status, "in_progress")
        self.client.post(url, {"status": "resolved"})
        req.refresh_from_db()
        self.assertEqual(req.status, "resolved")

    def test_status_change_requires_post(self):
        req = HelpRequest.objects.create(name="Marie", contact="m@x.ht", message="Aide")
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("dashboard:help_set_status", args=[req.pk])).status_code, 405)

    def test_admin_list_filters_by_status_and_shows_counts(self):
        HelpRequest.objects.create(name="Nouvelle Personne", contact="a@x.ht", message="m1")
        HelpRequest.objects.create(name="Personne Resolue", contact="b@x.ht", message="m2", status="resolved")
        self.client.force_login(self.admin)
        r = self.client.get(reverse("dashboard:help_list"), {"statut": "new"})
        self.assertContains(r, "Nouvelle Personne")
        self.assertNotContains(r, "Personne Resolue")
        self.assertEqual(self.client.get(reverse("dashboard:help_list"), {"statut": "bidon"}).context["status"], "")

    def test_admin_sidebar_and_home_show_new_requests(self):
        HelpRequest.objects.create(name="Marie", contact="m@x.ht", message="Aide")
        HelpRequest.objects.create(name="Paul", contact="p@x.ht", message="Aide", status="resolved")
        self.client.force_login(self.admin)
        r = self.client.get(reverse("dashboard:home"))
        self.assertContains(r, "1 demande d'aide nouvelle")
        self.assertContains(r, 'class="side-count"')

    def test_csv_export_is_filtered_and_safe_for_spreadsheets(self):
        HelpRequest.objects.create(name="Marie", contact="+509 3712 3456", topic="payment", message="=CMD()", status="new")
        HelpRequest.objects.create(name="Paul", contact="p@x.ht", message="Fait", status="resolved")
        self.client.force_login(self.admin)
        r = self.client.get(reverse("dashboard:help_export_csv"), {"statut": "new"})
        text = r.content.decode("utf-8")
        self.assertTrue(text.startswith("\ufeffReçue le;Nom;"))
        self.assertIn("Marie;+509 3712 3456;Un paiement ou un billet;'=CMD();Nouvelle", text)
        self.assertNotIn("Paul", text)
        self.assertIn("demandes-aide-eventlead.csv", r["Content-Disposition"])
        self.assertIn("Paul", self.client.get(reverse("dashboard:help_export_csv")).content.decode("utf-8"))


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

        call_command("seed_demo", stdout=open(os.devnull, "w"))

    def test_public_pages(self):
        event = Event.objects.public_active().first()
        for url in [reverse("core:landing"), reverse("core:help"), reverse("events:explore"), reverse("payments:ticketing"),
                    reverse("accounts:login"), reverse("accounts:register"), reverse("accounts:register_organizer"),
                    reverse("ads:list"), reverse("events:public_detail", args=[event.pk])]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_admin_pages(self):
        self.client.login(email="admin@eventlead.ht", password="EventLead2026!")
        event = Event.objects.get(title__startswith="Mariage")
        guest = event.guests.first()
        gift = event.gifts.first()
        ad = Ad.objects.first()
        category = EventCategory.objects.first()
        urls = [
            reverse("dashboard:home"), reverse("dashboard:event_list"), reverse("dashboard:event_create"),
            reverse("dashboard:event_detail", args=[event.pk]), reverse("dashboard:event_live", args=[event.pk]),
            reverse("dashboard:event_edit", args=[event.pk]), reverse("dashboard:guest_list"),
            reverse("dashboard:guest_list") + f"?event={event.pk}", reverse("dashboard:guest_create"),
            reverse("dashboard:guest_edit", args=[guest.pk]), reverse("dashboard:gift_list"),
            reverse("dashboard:gift_create"), reverse("dashboard:gift_edit", args=[gift.pk]),
            reverse("dashboard:ad_list"), reverse("dashboard:ad_create"), reverse("dashboard:ad_edit", args=[ad.pk]),
            reverse("dashboard:help_list"), reverse("dashboard:category_list"), reverse("dashboard:category_create"),
            reverse("dashboard:category_edit", args=[category.pk]),
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
