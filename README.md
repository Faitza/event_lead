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

Le jeu de démonstration contient 6 catégories (Mariage, Gala, Anniversaire, Baptême, Conférence, Concert), 6 événements rangés dans ces catégories (4 publics, un mariage privé, un anniversaire passé pour tester l'évaluation), 11 invités à différents statuts, 8 cadeaux sur le mariage (dont 4 déjà choisis), 3 publicités actives (une seule, « Pâtisserie Kay Dous », est dans la séquence après réponse), 3 avis, 4 paiements et 3 demandes d'aide (une nouvelle, une en cours, une résolue).

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
| `core` | Landing page (Accueil, événements publics, Services, À propos, Contact), `Review`, `ContactMessage`, `HelpRequest`, page Aide, tableau de bord admin, commande `seed_demo`, tests |
| `events` | `Event`, `EventCategory`, `Guest`, `EventEvaluation`, CRUD admin (événements, catégories, invités), exports CSV/PDF, géocodage, portail Organisateur, flux invité multi-étapes |
| `gifts` | `Gift`, `GiftClaim`, `services.py` (écriture atomique), gestion admin et export CSV |
| `ads` | `Ad`, page publicité avec compte à rebours, suivi des vues et clics |
| `payments` | `Payment`, billetterie, accès VIP, historique admin |

## Principales URLs

| URL | Rôle |
|---|---|
| `/` | Accueil : défilé des publications, événements publics et billets, puis services, avis et contact |
| `/connexion/`, `/inscription/`, `/inscription/organisateur/` | Authentification |
| `/admin-dashboard/` (+ `evenements/`, `categories/`, `invites/`, `cadeaux/`, `publicites/`, `paiements/`, `messages/`, `aide/`) | Administrateur |
| `/organisateur/` | Portail Organisateur VIP |
| `/organisateur/devenir-vip/` | Paiement de l'accès VIP |
| `/invitation/<uuid:token>/` | Flux invité (présence, cadeaux, récapitulatif, confirmation), sans compte ni connexion : le lien personnel suffit |
| `/invitation/<uuid:token>/publicite/<int:ad_id>/` | Page publicité |
| `/aide/` | Aide : questions fréquentes par profil, WhatsApp, formulaire « J'ai besoin d'aide » (`?sujet=` présélectionne le sujet) |
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

## Espace d'aide

- **Page Aide** (`/aide/`, lien dans le menu et le pied de page) : questions fréquentes classées par profil (invité ou visiteur, Organisateur VIP, équipe EventLead). Les textes sont dans `core/help.py` ; chaque question a un identifiant stable (`/aide/#faq-invite-cadeau` ouvre directement la réponse). Les réponses décrivent ce que fait le site aujourd'hui : à relire si le fonctionnement change.
- **Bouton WhatsApp flottant** sur toutes les pages publiques, avec le numéro de la page Contact (`CONTACT_WHATSAPP` dans `.env`). Il n'apparaît ni dans le tableau de bord ni dans le parcours d'invitation (où une ligne discrète « Une question ? » le remplace, pour ne pas gêner le bouton d'action).
- **Formulaire « J'ai besoin d'aide »** : nom, e-mail ou numéro, sujet, message. L'e-mail ou le numéro est vérifié, un champ piège écarte les robots. Chaque envoi crée une `HelpRequest` au statut « Nouvelle ».
- **Tableau de bord** (`/admin-dashboard/aide/`) : liste filtrable par statut (nouvelle, en cours, résolue), changement de statut en un clic, lien WhatsApp ou e-mail vers la personne, export CSV (`aide/export.csv`, protégé contre les formules de tableur), compteur dans le menu et sur l'accueil du tableau de bord.
- **Petites aides dans le parcours** : lignes repliées, sans bruit, à l'étape présence (« Pas de compte à créer ? »), à la liste des cadeaux, au récapitulatif, et dans la fenêtre de paiement (code reçu par SMS pour MonCash, lien « Demander de l'aide »). Elles renvoient vers la page Aide dans un nouvel onglet, pour ne pas perdre la réponse en cours. Pas de chat automatique.

## Règles métier du module cadeaux

- Les étapes cadeaux n'apparaissent que si l'invité répond « Oui » et que l'événement a au moins un cadeau.
- Les réservations utilisent le modèle `GiftClaim` (variante recommandée par le cahier des charges) : un cadeau est disponible tant que `claims.count() < quantity`. Il n'y a donc pas de champ `taken_by` sur `Gift`, l'information « qui a pris quoi » vit dans `GiftClaim`.
- La confirmation passe par `gifts.services.confirm_response` : `transaction.atomic()` + `select_for_update()` sur l'invité et chaque cadeau, vérification de la disponibilité sous verrou. Si un cadeau a été pris entre-temps, rien n'est écrit et l'invité revient à la liste avec un message.
- Une présence confirmée est définitive : aucune vue ni URL côté invité ne permet de modifier ou supprimer un `GiftClaim` (`GiftClaim` est en `on_delete=PROTECT`, l'admin Django en interdit aussi la suppression).
- L'invité voit seulement « Déjà pris » ; seul l'administrateur voit le nom du donateur.
- Un cadeau déjà choisi ne peut pas être supprimé ; sa quantité ne peut pas descendre sous le nombre déjà choisi.
- La liste se met à jour toutes les 5 secondes côté invité (polling `fetch()`), comme le suivi en direct côté admin.
- Un invité qui a répondu « Non » ou « Peut-être » peut revenir sur son lien et changer d'avis.

## Trois langues : français, anglais, créole haïtien

Le site existe en français (langue par défaut), en anglais et en créole haïtien (code `ht`, affiché « KR » dans le sélecteur **FR | EN | KR**).

- **Sélecteur** dans la barre du haut du site, du parcours d'invitation, des pages de connexion et du tableau de bord. Il marche sans compte : le choix est gardé dans un cookie, et sur le profil (`CustomUser.language`, aussi modifiable dans « Mon profil ») pour une personne connectée. Ordre de priorité : `?lang=xx` dans l'adresse, cookie, langue du profil, langue du navigateur, français.
- **Invitations** : chaque invité a sa langue (`Guest.language`, choisie dans le formulaire invité). Le message WhatsApp ou e-mail est écrit dans cette langue et le lien se termine par `?lang=xx`, si bien que la page s'ouvre dans la même langue, sans compte (`events/messaging.py`).
- **Ce qui est traduit** : tous les gabarits, formulaires, messages, textes d'aide, noms de catégories par défaut, en-têtes d'exports, dates (mois et jours en créole compris). Ce que les personnes saisissent (titres d'événements, noms de cadeaux, descriptions, avis, catégories créées par l'équipe) n'est jamais traduit.
- **Catalogues** : `locale/en` et `locale/ht` (fichiers `.po` à corriger, `.mo` compilés **versionnés** : Windows n'a pas besoin de gettext). Le texte d'origine dans le code est le français. Pas d'outil gettext requis : `python tools/i18n.py sync` relève les textes du code, met à jour les `.po` et recompile les `.mo` ; `python tools/i18n.py report` liste ce qui manque ; `python tools/i18n.py check` vérifie les variables. Après avoir corrigé un `.po` à la main : `python tools/i18n.py compile`.
- **Ajouter un texte** : écrire le texte français dans le code avec `{% trans "..." %}` (gabarits), `_("...")` (Python), puis lancer `python tools/i18n.py sync` et remplir les traductions vides des deux `.po` (un test échoue tant qu'il en manque).
- **Le créole est un brouillon** écrit par Claude : il doit être relu par une personne dont c'est la langue avant publication (les vocabulaires techniques comme « estati », « sote », « evalye », « dosye spam » en particulier).

## QR code d'entrée et pointage du jour J

- **Billet de l'invité** : chaque invité a un code d'entrée (`Guest.entry_code`, par exemple `EL-7K4Q-92MD`, sans caractères ambigus). Dès qu'il confirme sa présence, la page « C'est confirmé » propose « Voir mon QR code d'entrée » (aussi disponible en rouvrant son lien personnel) : billet avec le QR code, le nombre de personnes et le code lisible, bouton pour l'enregistrer en image dans le téléphone (il s'ouvre alors sans réseau) et bouton pour se l'envoyer par WhatsApp. Aucun compte n'est demandé. Le billet n'existe que pour un invité qui a confirmé.
- **Contenu du QR code** : l'adresse `/entree/<code>/`. Pour le public, cette page ne montre rien sur l'invité ; pour l'équipe connectée, elle affiche l'invité et un bouton « Valider l'entrée » (une simple ouverture ne valide jamais).
- **Pointage** (`/admin-dashboard/pointage/`, lien « Pointage » dans le menu et sur la fiche d'un événement) : chiffres en direct (arrivés, attendus, QR refusés, ajoutés sur place, barre « 87 sur 142 invités confirmés »), lecture du QR code avec la caméra (téléphone ou tablette ; il faut une adresse en https hors du poste local), recherche d'un invité par nom ou par code pour pointer à la main, ajout d'un invité arrivé sans être sur la liste (hors limite d'invités), annulation d'un pointage fait par erreur, plein écran. Un second passage du même QR est refusé (« QR déjà utilisé »), de même qu'un code inconnu ou celui d'un autre événement ; tout est gardé dans le journal `CheckIn`. La page se met à jour toute seule toutes les 5 secondes.
- La lecture du QR code utilise `BarcodeDetector` quand le navigateur l'a, sinon la bibliothèque jsQR (chargée depuis jsDelivr). La génération du QR code utilise `segno` (nouvelle dépendance : `pip install -r requirements.txt`).
- Après un `git pull` : `python manage.py migrate` (les invités déjà créés reçoivent leur code), puis `python manage.py seed_demo --reset` si vous voulez des données de démonstration neuves.

## Envoi des invitations (V1)

Chaque invité possède un `magic_token`. Dans `/admin-dashboard/invites/`, l'admin ouvre WhatsApp (`wa.me`) ou son client e-mail (`mailto:`) avec un message prérempli, dans la langue de l'invité, contenant le lien, ou copie le lien, puis marque l'invitation comme envoyée.

## Tests

```bash
python manage.py test
```

130 tests couvrent la règle « dernière unité », la transaction annulée en cas de conflit, le caractère définitif des réponses, le parcours invité complet jusqu'à la publicité puis l'accueil, le défilé de l'accueil, les redirections après connexion, les règles d'accès par rôle, le paiement VIP et l'affichage de chaque page principale, l'absence de connexion forcée sur le parcours invité et la page d'accueil publique, les catégories d'événements (gestion réservée à l'administrateur, filtre, badge, événements privés jamais exposés) l'espace d'aide (page, bouton WhatsApp, formulaire, statuts, export CSV, aides du parcours) le QR code d'entrée et le pointage (codes uniques, billet réservé aux présents, validation une seule fois, refus des codes inconnus ou d'un autre événement, ajout sur place, annulation, chiffres) et les trois langues (sélecteur, cookie, profil, `?lang=`, pages principales en anglais et en créole sans reste de français, message d'invitation par langue, catalogues complets).

## Production

- `DEBUG=False`, `SECRET_KEY`, `ALLOWED_HOSTS` et `DATABASE_URL` (PostgreSQL) dans l'environnement.
- `python manage.py collectstatic`, servir `staticfiles/` (WhiteNoise ou serveur web).
- Médias : définir `DEFAULT_FILE_STORAGE_BACKEND` (S3 via `django-storages`, ou Cloudinary) et installer le paquet correspondant.
- La photo en arche du haut de page, `static/img/photos/hero-arch.jpg` (portrait, environ 4/5, sans texte par-dessus), est une image générée par IA et fournie par le client (FAYaFA_Tech), simplement compressée en JPEG ; elle reçoit un léger voile violet en CSS. Remplacez ce fichier pour changer de photo. Les photos d'ambiance (`static/img/photos/`) sont des visuels de remplacement : remplacez-les par les photos du client (couvertures d'événements via l'admin, images de l'accueil dans `templates/core/landing.html`). Les polices sont chargées depuis Google Fonts.
