# EventLead

Plateforme web de gestion d'événements pour Haïti et la Caraïbe : invitations par WhatsApp ou e-mail avec lien magique, réponse multi-étapes, liste de cadeaux sans doublon, publicités partenaires, billetterie (MonCash, NatCash, carte, PayPal) et accès Organisateur VIP payant.

Stack : Python 3.11+, Django 5.1, PostgreSQL (SQLite en développement), django-allauth (Google), Leaflet + OpenStreetMap, geopy/Nominatim, xhtml2pdf, Bootstrap 5 + Bootstrap Icons. Interface 100 % en français, sans emoji.

## Démarrage rapide

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # puis adaptez les valeurs
python manage.py migrate
python manage.py seed_demo           # données de démonstration (facultatif)
python manage.py createsuperuser     # facultatif si vous utilisez seed_demo
python manage.py runserver
```

Ouvrez http://127.0.0.1:8000/.

### Comptes de démonstration (`seed_demo`)

Mot de passe commun : `EventLead2026!`

| Rôle | E-mail | Point d'entrée |
|---|---|---|
| Administrateur | `admin@eventlead.ht` | `/admin-dashboard/` |
| Organisateur VIP (payé) | `organisateur@eventlead.ht` | `/organisateur/` |
| Organisateur non payé | `nouveau.organisateur@eventlead.ht` | bloqué sur `/organisateur/devenir-vip/` |
| Invité | `invite@eventlead.ht` | `/mon-espace/` |

La commande affiche aussi un lien magique `/invitation/<uuid>/` d'un invité en attente pour tester le parcours complet sans connexion. `python manage.py seed_demo --reset` repart de zéro.

Le jeu de démonstration contient 5 événements (3 publics, un mariage privé, un anniversaire passé pour tester l'évaluation), 11 invités à différents statuts, 8 cadeaux sur le mariage (dont 4 déjà choisis), 2 publicités actives, 3 avis et 4 paiements.

## Paiements en mode démo

`PAYMENT_DEMO_MODE=True` (par défaut) : aucune API réelle n'est appelée.

- MonCash : n'importe quel numéro haïtien valide, code OTP `123456` (un autre code enregistre un paiement échoué).
- NatCash : numéro + PIN à 4 chiffres.
- Carte (Stripe) : `4242 4242 4242 4242` acceptée, `4000 0000 0000 0002` refusée, date future, CVC à 3 chiffres.
- PayPal : e-mail + mot de passe quelconques.

Références générées : `MC-XXXXXX`, `NAT-XXXXXX`, `ST-XXXXXX`, `PP-XXXXXX`. Taux fixe 1 HTG = 0,0075 USD (`HTG_TO_USD_RATE` dans `settings.py`). Les vraies intégrations se branchent dans `payments/gateways.py` ; les clés sont lues uniquement depuis l'environnement.

## Connexion Google

1. Créez un ID client OAuth sur Google Cloud Console.
2. URI de redirection : `http://localhost:8000/accounts/google/login/callback/` (et l'équivalent en production).
3. Renseignez `GOOGLE_CLIENT_ID` et `GOOGLE_CLIENT_SECRET` dans `.env`.

Sans ces valeurs, le bouton « Continuer avec Google » est affiché désactivé. Un nouvel utilisateur Google reçoit le rôle invité et ses invitations existantes (même e-mail) lui sont rattachées automatiquement.

## Structure

| App | Contenu |
|---|---|
| `accounts` | `CustomUser` (rôle, téléphone, avatar, `is_vip`), connexion e-mail, inscription invité / organisateur, décorateurs `@role_required` et `@vip_organizer_required` |
| `core` | Landing page (Accueil, événements publics, Services, À propos, Contact), `Review`, `ContactMessage`, tableau de bord admin, commande `seed_demo`, tests |
| `events` | `Event`, `Guest`, `EventEvaluation`, CRUD admin, exports CSV/PDF, géocodage, portail Organisateur, flux invité multi-étapes |
| `gifts` | `Gift`, `GiftClaim`, `services.py` (écriture atomique), gestion admin et export CSV |
| `ads` | `Ad`, page publicité avec compte à rebours, suivi des vues et clics |
| `payments` | `Payment`, billetterie, accès VIP, historique admin |

## Principales URLs

| URL | Rôle |
|---|---|
| `/` | Landing page publique |
| `/connexion/`, `/inscription/`, `/inscription/organisateur/` | Authentification |
| `/admin-dashboard/` (+ `evenements/`, `invites/`, `cadeaux/`, `publicites/`, `paiements/`, `messages/`) | Administrateur |
| `/organisateur/` | Portail Organisateur VIP |
| `/organisateur/devenir-vip/` | Paiement de l'accès VIP |
| `/invitation/<uuid:token>/` | Flux invité (présence, cadeaux, récapitulatif, confirmation) |
| `/invitation/<uuid:token>/publicite/<int:ad_id>/` | Page publicité |
| `/evenements/` | Exploration des événements publics |
| `/billetterie/` | Billetterie |
| `/django-admin/` | Back-office Django natif |

## Règles métier du module cadeaux

- Les étapes cadeaux n'apparaissent que si l'invité répond « Oui » et que l'événement a au moins un cadeau.
- Les réservations utilisent le modèle `GiftClaim` (variante recommandée par le cahier des charges) : un cadeau est disponible tant que `claims.count() < quantity`. Il n'y a donc pas de champ `taken_by` sur `Gift`, l'information « qui a pris quoi » vit dans `GiftClaim`.
- La confirmation passe par `gifts.services.confirm_response` : `transaction.atomic()` + `select_for_update()` sur l'invité et chaque cadeau, vérification de la disponibilité sous verrou. Si un cadeau a été pris entre-temps, rien n'est écrit et l'invité revient à la liste avec un message.
- Une présence confirmée est définitive : aucune vue ni URL côté invité ne permet de modifier ou supprimer un `GiftClaim` (`GiftClaim` est en `on_delete=PROTECT`, l'admin Django en interdit aussi la suppression).
- L'invité voit seulement « Déjà pris » ; seul l'administrateur voit le nom du donateur.
- Un cadeau déjà choisi ne peut pas être supprimé ; sa quantité ne peut pas descendre sous le nombre déjà choisi.
- La liste se met à jour toutes les 5 secondes côté invité (polling `fetch()`), comme le suivi en direct côté admin.
- Un invité qui a répondu « Non » ou « Peut-être » peut revenir sur son lien et changer d'avis.

## Envoi des invitations (V1)

Chaque invité possède un `magic_token`. Dans `/admin-dashboard/invites/`, l'admin ouvre WhatsApp (`wa.me`) ou son client e-mail (`mailto:`) avec un message prérempli contenant le lien, ou copie le lien, puis marque l'invitation comme envoyée.

## Tests

```bash
python manage.py test
```

25 tests couvrent la règle « dernière unité », la transaction annulée en cas de conflit, le caractère définitif des réponses, le parcours invité complet jusqu'à la publicité, les règles d'accès par rôle, le paiement VIP et l'affichage de chaque page principale.

## Production

- `DEBUG=False`, `SECRET_KEY`, `ALLOWED_HOSTS` et `DATABASE_URL` (PostgreSQL) dans l'environnement.
- `python manage.py collectstatic`, servir `staticfiles/` (WhiteNoise ou serveur web).
- Médias : définir `DEFAULT_FILE_STORAGE_BACKEND` (S3 via `django-storages`, ou Cloudinary) et installer le paquet correspondant.
- Les photos d'ambiance sont des placeholders Unsplash ; remplacez-les par les photos du client (couvertures d'événements via l'admin, images de la landing dans `templates/core/landing.html`).
# event_lead
