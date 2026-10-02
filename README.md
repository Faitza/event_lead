# EventLead

Plateforme web de gestion d'événements pour Haïti et la Caraïbe : invitations par WhatsApp ou e-mail avec lien magique, réponse multi-étapes, liste de cadeaux sans doublon, publicités partenaires, billetterie (MonCash, NatCash, carte, PayPal) et accès Organisateur VIP payant.

Stack : Python 3.11+, Django 5.1, PostgreSQL (SQLite en développement), django-allauth (Google), Leaflet + OpenStreetMap, geopy/Nominatim, xhtml2pdf, Bootstrap 5 + Bootstrap Icons. Interface 100 % en français, sans emoji.

Direction visuelle « carton d'invitation de gala » : Bodoni Moda + Jost, filets et losanges dorés, photos en arche, billets perforés, logo d'origine (`EventLead.png`) sans aucune retouche du dessin, simplement rogné aux bords blancs (`static/img/eventlead-mark.png`, avec le petit « EventLead » en script au centre et le L coupé comme l'original), toujours sur fond blanc (barres blanches, badge blanc du pied de page), avec le nom « EventLead » écrit en texte à côté (Bodoni Moda 600). Les jetons de design sont dans `static/css/eventlead.css`.

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
| Administrateur | `admin@eventlead.ht` | `/admin-dashboard/` après connexion |
| Organisateur VIP (payé) | `organisateur@eventlead.ht` | accueil `/` après connexion, portail `/organisateur/` via « Mon espace » |
| Organisateur non payé | `nouveau.organisateur@eventlead.ht` | bloqué sur `/organisateur/devenir-vip/` |
| Invité | `invite@eventlead.ht` | accueil `/` après connexion, `/mon-espace/` via « Mon espace » |

La commande affiche aussi un lien magique `/invitation/<uuid>/` d'un invité en attente pour tester le parcours complet sans connexion. `python manage.py seed_demo --reset` repart de zéro.

Le jeu de démonstration contient 6 catégories (Mariage, Gala, Anniversaire, Baptême, Conférence, Concert), 6 événements rangés dans ces catégories (4 publics, un mariage privé, un anniversaire passé pour tester l'évaluation), 11 invités à différents statuts, 8 cadeaux sur le mariage (dont 4 déjà choisis), 3 publicités actives (une seule, « Pâtisserie Kay Dous », est dans la séquence après réponse), 3 avis et 4 paiements.

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
| `events` | `Event`, `EventCategory`, `Guest`, `EventEvaluation`, CRUD admin (événements, catégories, invités), exports CSV/PDF, géocodage, portail Organisateur, flux invité multi-étapes |
| `gifts` | `Gift`, `GiftClaim`, `services.py` (écriture atomique), gestion admin et export CSV |
| `ads` | `Ad`, page publicité avec compte à rebours, suivi des vues et clics |
| `payments` | `Payment`, billetterie, accès VIP, historique admin |

## Principales URLs

| URL | Rôle |
|---|---|
| `/` | Accueil : défilé des publications, événements publics et billets, puis services, avis et contact |
| `/connexion/`, `/inscription/`, `/inscription/organisateur/` | Authentification |
| `/admin-dashboard/` (+ `evenements/`, `categories/`, `invites/`, `cadeaux/`, `publicites/`, `paiements/`, `messages/`) | Administrateur |
| `/organisateur/` | Portail Organisateur VIP |
| `/organisateur/devenir-vip/` | Paiement de l'accès VIP |
| `/invitation/<uuid:token>/` | Flux invité (présence, cadeaux, récapitulatif, confirmation), sans compte ni connexion : le lien personnel suffit |
| `/invitation/<uuid:token>/publicite/<int:ad_id>/` | Page publicité |
| `/evenements/` (+ `?categorie=<identifiant>`) | Exploration des événements publics, filtrable par catégorie |
| `/billetterie/` | Billetterie |
| `/django-admin/` | Back-office Django natif |

## Parcours après une réponse à une invitation

1. L'invité confirme sa réponse (`/invitation/<uuid>/recapitulatif/`).
2. Redirection automatique vers la première publicité marquée « afficher après la réponse » (`/invitation/<uuid>/publicite/<id>/`), avec le message de remerciement. Le bouton « Passer » s'active après le compte à rebours et enchaîne les publicités suivantes.
3. Fin de séquence, ou aucune publicité active : redirection vers l'accueil (`/#affiche`), où se trouvent le défilé et les événements publics.

## Accueil et défilé

Pour un visiteur non connecté, l'accueil s'ouvre sur un titre d'accroche, puis une bande « Comment ça marche » en trois étapes (inviter, répondre en un lien, cadeaux sans doublon). Les textes de la page publique sont réunis dans `marketing/landing.md` (projet partagé) ; aucun chiffre promotionnel n'est affiché sans source dans les données. Le pied de page est celui de la première version (quatre colonnes), avec le logo clair et le nom écrit en texte.

La page d'accueil affiche un défilé qui alterne publications actives, événements publics à venir et billets (événements publics payants, avec prix en HTG et en USD). Il se met en pause au survol, au focus clavier ou avec le bouton « Mettre en pause », et devient une bande défilable à la main si l'utilisateur préfère les animations réduites. Après connexion, un invité ou un organisateur VIP arrive sur cet accueil, avec un bandeau de bienvenue à la place du grand héros ; l'administrateur arrive sur son tableau de bord.

## Catégories d'événements

Un événement peut avoir une catégorie (`Event.category`, facultative). L'administrateur gère les catégories dans `/admin-dashboard/categories/` (nom, icône Bootstrap Icons, ordre d'affichage) et choisit la catégorie dans le formulaire d'événement. Supprimer une catégorie ne supprime pas ses événements : ils n'ont simplement plus de catégorie. Sur l'accueil et sur `/evenements/`, une rangée de filtres au-dessus des événements publics (`?categorie=<identifiant>`, filtre côté serveur) ne propose que les catégories qui ont au moins un événement public à venir ; chaque carte d'événement porte un badge de catégorie. Un identifiant inconnu est ignoré. Le défilé « À l'affiche » n'est pas filtré. Après un `git pull`, lancez `python manage.py migrate` ; `python manage.py seed_demo --reset` recrée les catégories de démonstration.

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

50 tests couvrent la règle « dernière unité », la transaction annulée en cas de conflit, le caractère définitif des réponses, le parcours invité complet jusqu'à la publicité puis l'accueil, le défilé de l'accueil, les redirections après connexion, les règles d'accès par rôle, le paiement VIP et l'affichage de chaque page principale, l'absence de connexion forcée sur le parcours invité et la page d'accueil publique, et les catégories d'événements (gestion réservée à l'administrateur, filtre, badge, événements privés jamais exposés).

## Production

- `DEBUG=False`, `SECRET_KEY`, `ALLOWED_HOSTS` et `DATABASE_URL` (PostgreSQL) dans l'environnement.
- `python manage.py collectstatic`, servir `staticfiles/` (WhiteNoise ou serveur web).
- Médias : définir `DEFAULT_FILE_STORAGE_BACKEND` (S3 via `django-storages`, ou Cloudinary) et installer le paquet correspondant.
- La photo en arche du haut de page, `static/img/photos/hero-arch.jpg` (portrait, environ 4/5, sans texte par-dessus), est une image générée par IA et fournie par le client (FAYaFA_Tech), simplement compressée en JPEG ; elle reçoit un léger voile violet en CSS. Remplacez ce fichier pour changer de photo. Les photos d'ambiance (`static/img/photos/`) sont des visuels de remplacement : remplacez-les par les photos du client (couvertures d'événements via l'admin, images de l'accueil dans `templates/core/landing.html`). Les polices sont chargées depuis Google Fonts.
