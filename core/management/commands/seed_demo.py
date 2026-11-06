"""Données de démonstration EventLead.

Usage : python manage.py seed_demo [--reset]
"""
from datetime import time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import CustomUser
from ads.models import Ad
from core.models import ContactMessage, HelpRequest, Review
from events import album
from events.models import DEFAULT_CATEGORIES, Event, EventCategory, EventEvaluation, Guest, Reminder, Table
from gifts.models import Gift, GiftClaim
from payments.models import Contribution, Payment

DEMO_PASSWORD = "EventLead2026!"


class Command(BaseCommand):
    help = "Crée des données de démonstration (événements, invités, cadeaux, publicités, avis, paiements)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Supprime d'abord les données existantes.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            GiftClaim.objects.all().delete()
            Contribution.objects.all().delete()
            Payment.objects.all().delete()
            Event.objects.all().delete()
            EventCategory.objects.all().delete()
            Ad.objects.all().delete()
            Review.objects.all().delete()
            ContactMessage.objects.all().delete()
            HelpRequest.objects.all().delete()
            CustomUser.objects.filter(email__endswith="@eventlead.ht").delete()

        if Event.objects.exists():
            self.stdout.write(self.style.WARNING("Des événements existent déjà. Relancez avec --reset pour repartir de zéro."))
            return

        today = timezone.localdate()

        def user(email, first, last, role, **extra):
            u = CustomUser(username=email, email=email, first_name=first, last_name=last, role=role, **extra)
            u.set_password(DEMO_PASSWORD)
            u.save()
            return u

        admin = user("admin@eventlead.ht", "Faitza", "Admin", "admin", is_staff=True, is_superuser=True)
        vip = user("organisateur@eventlead.ht", "Jonathan", "Pierre", "organizer", is_vip=True,
                   vip_since=timezone.now() - timedelta(days=20), phone="+509 3712 4455")
        user("nouveau.organisateur@eventlead.ht", "Mika", "Joseph", "organizer")
        guest_user = user("invite@eventlead.ht", "Nadège", "Louis", "guest", phone="+509 4011 2233")

        # ------------------------------------------------------------------ Catégories
        category_specs = DEFAULT_CATEGORIES
        cat = {
            name: EventCategory.objects.update_or_create(name=name, defaults={"icon_name": icon, "order": i})[0]
            for i, (name, icon) in enumerate(category_specs, start=1)
        }

        # ------------------------------------------------------------------ Événements
        gala = Event.objects.create(
            title="Gala de la Saint-Valentin", event_type="public", status="active",
            date=today + timedelta(days=18), time=time(19, 30),
            venue="Hôtel Montana, Rue F. Cardozo, Pétion-Ville", latitude=18.5126, longitude=-72.2885,
            max_guests=300, evaluation_delay_days=2, price_htg=Decimal("3500"), created_by=admin, category=cat["Gala"],
            description="Dîner de gala, orchestre live et piste de danse sous les étoiles de Pétion-Ville. Tenue de soirée exigée.",
        )
        concert = Event.objects.create(
            title="Festival Kompa sur la plage", event_type="public", status="active",
            date=today + timedelta(days=32), time=time(16, 0),
            venue="Wahoo Bay Beach, Route Nationale 1, Arcahaie", latitude=18.8133, longitude=-72.5272,
            max_guests=1500, price_htg=Decimal("1500"), created_by=admin, category=cat["Concert"],
            description="Les meilleurs groupes de kompa réunis pour une après-midi et une soirée au bord de la mer.",
        )
        Event.objects.create(
            title="Conférence Entreprendre en Haïti", event_type="public", status="active",
            date=today + timedelta(days=45), time=time(9, 0),
            venue="Marriott Port-au-Prince, Avenue Jean-Paul II, Turgeau", latitude=18.5333, longitude=-72.3243,
            max_guests=250, created_by=admin, category=cat["Conférence"],
            description="Une journée de rencontres et d'ateliers avec des entrepreneurs haïtiens et de la diaspora.",
        )
        Event.objects.create(
            title="Concert de la chorale Voix d'Espérance", event_type="public", status="active",
            date=today + timedelta(days=25), time=time(18, 0),
            venue="Église du Sacré-Cœur, Turgeau, Port-au-Prince", latitude=18.5372, longitude=-72.3167,
            max_guests=400, created_by=admin, category=cat["Concert"],
            description="Une soirée de chants et de louanges, entrée libre. Venez en famille.",
        )
        wedding = Event.objects.create(
            title="Mariage de Sarah et Jean-Marc", event_type="private", status="active",
            date=today + timedelta(days=60), time=time(15, 0),
            venue="Église Saint-Pierre, Place Saint-Pierre, Pétion-Ville", latitude=18.5118, longitude=-72.2856,
            max_guests=180, allow_companions=True, max_companions=2, evaluation_delay_days=3, created_by=admin,
            category=cat["Mariage"],
            description="Cérémonie religieuse à 15h, suivie de la réception au jardin de l'Hôtel Montana. Merci de confirmer votre présence avant le 15 du mois.",
        )
        anniversary = Event.objects.create(
            title="Anniversaire de Mme Duval - 60 ans", event_type="private", status="active",
            date=today - timedelta(days=7), time=time(18, 0),
            venue="Restaurant Quartier Latin, Pétion-Ville", latitude=18.5108, longitude=-72.2870,
            max_guests=60, evaluation_delay_days=3, created_by=admin, category=cat["Anniversaire"],
            description="Dîner surprise pour les 60 ans de Mme Duval.",
        )

        # ------------------------------------------------------------------ Invités du mariage
        wedding_guests = [
            ("Nadège Louis", "invite@eventlead.ht", "+509 4011 2233", "email", "confirmed", 1, guest_user),
            ("Jonathan Pierre", "organisateur@eventlead.ht", "+509 3712 4455", "whatsapp", "confirmed", 0, vip),
            ("Roseline Augustin", "roseline@example.com", "+509 3455 6677", "whatsapp", "confirmed", 2, None),
            ("Patrick Étienne", "patrick@example.com", "+509 3888 1212", "whatsapp", "maybe", 0, None),
            ("Claudine Joseph", "claudine@example.com", "", "email", "declined", 0, None),
            ("Wilson Charles", "", "+509 3123 9090", "whatsapp", "pending", 0, None),
            ("Marie-Ange Dorvil", "marieange@example.com", "+509 3600 4545", "email", "pending", 0, None),
            ("Junior Baptiste", "", "+509 4789 0011", "whatsapp", "pending", 0, None),
        ]
        guests = {}
        for name, email, phone, via, status, comp, linked in wedding_guests:
            g = Guest.objects.create(
                event=wedding, name=name, email=email, phone=phone, sent_via=via, status=status,
                companions=comp, user=linked,
                invitation_sent_at=timezone.now() - timedelta(days=5),
                replied_at=timezone.now() - timedelta(hours=len(guests) * 7 + 2) if status != "pending" else None,
                wants_gift=True if status == "confirmed" else None,
            )
            guests[name] = g
        # Quelques invités reçoivent leur invitation en anglais ou en créole
        Guest.objects.filter(event=wedding, name="Patrick Étienne").update(language="en")
        Guest.objects.filter(event=wedding, name="Junior Baptiste").update(language="ht")

        # Plan de table : 12 tables de 12 places, quelques invités déjà placés
        seat_tables = [Table(event=wedding, number=i, capacity=12, name="Table d'honneur" if i == 1 else "") for i in range(1, 13)]
        Table.objects.bulk_create(seat_tables)
        first = Table.objects.get(event=wedding, number=1)
        Guest.objects.filter(pk__in=[guests["Nadège Louis"].pk, guests["Jonathan Pierre"].pk]).update(table=first)

        # Une relance déjà partie, pour montrer l'historique sur la page des relances
        Reminder.objects.create(guest=guests["Wilson Charles"], channel="whatsapp", sent_by=admin, sent_at=timezone.now() - timedelta(days=1))

        # Liste de 8 cadeaux
        gift_specs = [
            ("Service à café en porcelaine", "bi-cup-hot", 1),
            ("Batterie de cuisine", "bi-egg-fried", 1),
            ("Lot de verres en cristal", "bi-cup-straw", 2),
            ("Lampe de salon", "bi-lamp", 1),
            ("Enceinte Bluetooth", "bi-speaker", 1),
            ("Week-end à Labadee", "bi-airplane", 1),
            ("Appareil photo instantané", "bi-camera", 1),
            ("Bouquet de fleurs du jardin", "bi-flower1", 3),
        ]
        gifts = {name: Gift.objects.create(event=wedding, name=name, icon_name=icon, quantity=qty)
                 for name, icon, qty in gift_specs}
        GiftClaim.objects.create(gift=gifts["Service à café en porcelaine"], guest=guests["Roseline Augustin"])
        GiftClaim.objects.create(gift=gifts["Lot de verres en cristal"], guest=guests["Roseline Augustin"])
        GiftClaim.objects.create(gift=gifts["Enceinte Bluetooth"], guest=guests["Nadège Louis"])
        GiftClaim.objects.create(gift=gifts["Bouquet de fleurs du jardin"], guest=guests["Jonathan Pierre"])

        # Contribution en argent à la place d'un cadeau (acceptée pour le mariage)
        Event.objects.filter(pk=wedding.pk).update(accept_contributions=True)
        donor = Guest.objects.create(
            event=wedding, name="Fabiola Désir", email="fabiola@example.com", phone="+509 3344 5566", sent_via="whatsapp",
            status="confirmed", companions=1, wants_gift=False, invitation_sent_at=timezone.now() - timedelta(days=5),
            replied_at=timezone.now() - timedelta(hours=30),
        )
        gift_payment = Payment.objects.create(
            kind="contribution", event=wedding, guest=donor, method="moncash", amount_htg=5000,
            reference=Payment.generate_reference("moncash"), status="success", payer_detail="+509 **** 5566",
        )
        Contribution.objects.create(
            event=wedding, guest=donor, payment=gift_payment, amount_htg=5000, message="Félicitations, tous nos vœux de bonheur !",
        )

        # Événement passé : l'organisateur VIP peut l'évaluer (délai écoulé)
        Guest.objects.create(event=anniversary, name="Jonathan Pierre", email="organisateur@eventlead.ht",
                             user=vip, sent_via="email", status="confirmed", replied_at=timezone.now() - timedelta(days=12))
        nadege = Guest.objects.create(event=anniversary, name="Nadège Louis", email="invite@eventlead.ht",
                                      user=guest_user, sent_via="email", status="confirmed", replied_at=timezone.now() - timedelta(days=11))
        # Remerciements publiés avec un petit album (photos du site), dont deux ajoutées par Nadège
        basket = Gift.objects.create(event=anniversary, name="Panier de fruits", icon_name="bi-basket", quantity=1)
        GiftClaim.objects.create(gift=basket, guest=nadege)
        anniversary.thanks_message = (
            "Merci d'avoir fêté mes 60 ans avec moi. Votre présence m'a profondément touchée. "
            "Voici quelques photos de la journée : ajoutez aussi les vôtres !"
        )
        anniversary.thanks_published_at = timezone.now() - timedelta(days=2)
        anniversary.save(update_fields=["thanks_message", "thanks_published_at"])
        demo_photos = ["event-gala", "event-kompa", "event-salon", "event-chorale", "about", "login", "hero-bg", "ad-patisserie"]
        for number, name in enumerate(demo_photos):
            source = settings.BASE_DIR / "static" / "img" / "photos" / f"{name}.jpg"
            if source.exists():
                with source.open("rb") as handle:
                    uploaded = ContentFile(handle.read(), name=f"{name}.jpg")
                    uploaded.size = len(uploaded)
                    album.add_photos(anniversary, [uploaded], nadege if number in (2, 5) else None)
        Guest.objects.create(event=gala, name="Nadège Louis", email="invite@eventlead.ht", user=guest_user,
                             sent_via="email", status="pending")

        # ------------------------------------------------------------------ Publicités
        patisserie = Ad.objects.create(
            advertiser="Pâtisserie Kay Dous", is_paid=True,
            title="Pâtisserie Kay Dous", icon_name="bi-cake2", order=0, skip_after_seconds=5,
            message="Pièces montées et gâteaux de mariage à Pétion-Ville. -10 % pour les invités EventLead.",
            sponsor_link="https://example.com/kay-dous", views=1204, clicks=96,
        )
        photo = settings.BASE_DIR / "static" / "img" / "photos" / "ad-patisserie.jpg"
        if photo.exists():
            patisserie.image.save("kay-dous.jpg", ContentFile(photo.read_bytes()), save=True)
        Ad.objects.create(
            advertiser="Fleurs de la Caraïbe", is_paid=True,
            title="Fleurs de la Caraïbe", icon_name="bi-flower1", order=1, skip_after_seconds=5,
            message="Compositions florales pour mariages et galas, livrées partout à Port-au-Prince. -15 % avec le code EVENTLEAD.",
            sponsor_link="https://example.com/fleurs-caraibe", views=842, clicks=67, show_after_reply=False,
        )
        Ad.objects.create(
            advertiser="Studio Lumière Photo", is_paid=True,
            title="Studio Lumière Photo", icon_name="bi-camera", order=2, skip_after_seconds=5,
            message="Photographes et vidéastes professionnels : immortalisez chaque instant de votre événement.",
            sponsor_link="https://example.com/studio-lumiere", views=615, clicks=41, show_after_reply=False,
        )

        # ------------------------------------------------------------------ Avis
        # Avis d'exemple pour tester la validation dans le tableau de bord : jamais publiés, ce ne sont pas de vrais clients.
        Review.objects.create(name="Exemple (avis de test)", stars=5, is_published=False,
                              text="Avis de démonstration : à valider ou à supprimer dans le tableau de bord, page Messages et avis.")

        # ------------------------------------------------------------------ Paiements
        Payment.objects.create(kind="organizer_access", user=vip, method="moncash", amount_htg=Decimal("5000"),
                               reference="MC-5A1B2C", status="success", payer_detail="+509 **** 4455")
        Payment.objects.create(kind="ticket", event=gala, user=guest_user, method="natcash", amount_htg=Decimal("7000"),
                               quantity=2, reference="NAT-3F9D10", status="success", payer_detail="+509 **** 2233")
        Payment.objects.create(kind="ticket", event=concert, user=guest_user, method="stripe", amount_htg=Decimal("1500"),
                               reference="ST-8E7A21", status="failed", payer_detail="Carte **** 0002")
        Payment.objects.create(kind="ticket", event=concert, user=vip, method="paypal", amount_htg=Decimal("3000"),
                               quantity=2, reference="PP-C4D2E8", status="success", payer_detail="jonathan@example.com")

        ContactMessage.objects.create(name="Stéphanie Noël", email="stephanie@example.com", phone="+509 3333 4444",
                                      message="Bonjour, je prépare un baptême pour 80 personnes en mars. Pouvez-vous m'envoyer une démonstration ?")

        help_specs = [
            ("Marie-Ange Dorvil", "marieange@example.com", "invitation", "in_progress", 30,
             "Je n'arrive pas à retrouver mon lien d'invitation pour le mariage de Sarah et Jean-Marc. Pouvez-vous me le renvoyer ?"),
            ("Roseline Augustin", "+509 3455 6677", "gift", "resolved", 50,
             "J'ai choisi un cadeau par erreur. Est-il possible de le changer ?"),
            ("Patrick Étienne", "+509 3888 1212", "payment", "new", 3,
             "Je n'ai pas reçu le code par SMS en payant mon billet avec MonCash. Que faire ?"),
        ]
        for name, contact, topic, status, hours_ago, message in help_specs:
            req = HelpRequest.objects.create(name=name, contact=contact, topic=topic, status=status, message=message)
            HelpRequest.objects.filter(pk=req.pk).update(created_at=timezone.now() - timedelta(hours=hours_ago))

        wedding_guest = guests["Wilson Charles"]
        self.stdout.write(self.style.SUCCESS("Données de démonstration créées."))
        self.stdout.write(f"  Mot de passe de tous les comptes : {DEMO_PASSWORD}")
        self.stdout.write("  Admin             : admin@eventlead.ht")
        self.stdout.write("  Organisateur VIP  : organisateur@eventlead.ht")
        self.stdout.write("  Organisateur non payé : nouveau.organisateur@eventlead.ht")
        self.stdout.write("  Invité            : invite@eventlead.ht")
        self.stdout.write(f"  Lien magique (invité en attente, mariage) : /invitation/{wedding_guest.magic_token}/")
