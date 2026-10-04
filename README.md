# EventLead

Plateforme web de gestion d'événements pour Haïti et la Caraïbe : invitations par WhatsApp ou e-mail avec lien magique, réponse multi-étapes, liste de cadeaux sans doublon, publicités partenaires, billetterie (MonCash, NatCash, carte, PayPal) et accès Organisateur VIP payant.

Stack : Python 3.11+, Django 5.1, PostgreSQL (SQLite en développement), django-allauth (Google), Leaflet + OpenStreetMap, geopy/Nominatim, xhtml2pdf, Bootstrap 5 + Bootstrap Icons. Interface 100 % en français, sans emoji.

Direction visuelle « carton d'invitation de gala » : Old Standard TT (titres et chiffres) + Jost (texte), filets et losanges dorés, photos en arche, billets perforés, logo d'origine (`EventLead.png`) sans aucune retouche du dessin, simplement rogné aux bords blancs (`static/img/eventlead-mark.png`, avec le petit « EventLead » en script au centre et le L coupé comme l'original), toujours sur fond blanc (barres blanches, badge blanc du pied de page), avec le nom « EventLead » écrit en texte à côté (police des titres, graisse 600). Les jetons de design sont dans `static/css/eventlead.css`.

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

Le jeu de démonstration contient 6 catégories (Mariage, Gala, Anniversaire, Baptême, Conférence, Concert), 6 événements rangés dans ces catégories (4 publics, un mariage privé, un anniversaire passé pour tester l'évaluation et les remerciements avec album), 12 invités à différents statuts, 9 cadeaux (8 sur le mariage, dont 4 déjà choisis, et un sur l'anniversaire), 3 publicités actives (une seule, « Pâtisserie Kay Dous », est dans la séquence après réponse), 3 avis, 5 paiements (dont une contribution en argent) et 3 demandes d'aide (une nouvelle, une en cours, une résolue).

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
| `/` | Accueil : défilé des publications, événements publics et billets, puis services (une photo par service, `static/img/photos/svc-*.jpg`), avis et contact |
| `/connexion/`, `/inscription/`, `/inscription/organisateur/` | Authentification |
| `/admin-dashboard/` (+ `evenements/`, `categories/`, `invites/`, `cadeaux/`, `publicites/`, `paiements/`, `messages/`, `aide/`, `pointage/`, `relances/`, `plan-de-table/`, `remerciements/`) | Administrateur |
| `/organisateur/` | Portail Organisateur VIP |
| `/organisateur/devenir-vip/` | Paiement de l'accès VIP |
| `/invitation/<uuid:token>/` | Flux invité (présence, cadeaux, récapitulatif, confirmation), sans compte ni connexion : le lien personnel suffit |
| `/invitation/<uuid:token>/contribution/` | Contribution en argent (MonCash ou NatCash) à la place d'un cadeau, si l'événement l'accepte |
| `/invitation/<uuid:token>/remerciements/` (+ `album.zip`) | Page « Merci » et album partagé, pour les invités présents, une fois publiés par l'équipe |
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

## Plan de table

- **Page « Plan de table »** (`/admin-dashboard/plan-de-table/`, lien dans le menu) : choisissez un événement. À gauche, les invités qui ont confirmé et n'ont pas encore de table (« Sans table ») ; à droite, les tables autour de la scène et de la piste de danse, avec « 9 / 12 places », « Complète » ou « 3 libres ». Chiffres en haut : tables, places (dont libres), personnes placées, invités sans table.
- **Placer un invité** : glissez-le sur une table (ordinateur), ou choisissez une table dans la liste « Placer à... » (téléphone et tablette, où le glisser-déposer n'existe pas). Pour le déplacer, glissez-le vers une autre table ; la croix le remet dans « Sans table ». Un invité et ses accompagnants restent ensemble : il prend autant de places que de personnes, et une table n'accepte jamais plus de personnes que de places.
- **Qui est placé** : seulement les invités qui ont confirmé. Un invité qui n'est plus « Présent » perd sa place automatiquement.
- **Tables** : « Ajouter une table » (nom facultatif, de 1 à 30 places), crayon pour renommer ou changer les places (refusé si des personnes y sont déjà plus nombreuses que le nouveau nombre de places), suppression (ses invités retournent dans « Sans table »). Sans table, la page propose de créer d'un coup 12 tables de 12 places (nombre et places modifiables). Le numéro d'une table ne change jamais, même si d'autres tables sont supprimées, car il est imprimé sur les billets.
- **Placement automatique** : place tous les invités sans table, sans déplacer ceux qui sont déjà placés. Les plus grands groupes d'abord, chacun à la table où il rentre le plus juste (les tables se remplissent donc l'une après l'autre) ; ceux qui ne trouvent pas de place sont comptés et il faut ajouter une table.
- **Imprimer le plan** : page propre, sans menu, avec les tables et leurs invités puis la liste « Sans table ».
- **Numéro de table sur le billet** : la page « Votre billet d'entrée » de l'invité affiche « Table 4 » (avec le nom de la table s'il y en a un), et l'écran de pointage de l'entrée l'affiche aussi après la lecture du QR code, pour guider l'invité jusqu'à sa table.
- Après un `git pull` : `python manage.py migrate` (nouvelle table `Table`), puis `python manage.py seed_demo --reset` si vous voulez des données neuves (le mariage de démonstration a 12 tables de 12 places, deux invités déjà placés).

## Relances des invités sans réponse

- **Page « Relances »** (`/admin-dashboard/relances/`, lien dans le menu) : choisissez un événement. On y voit combien d'invités n'ont pas répondu, combien n'ont jamais été relancés, combien l'ont été une, deux ou trois fois, la date de la prochaine relance, et la liste des invités sans réponse (canal, relances `n/3`, prochaine date, statut « À relancer », « Relancé N fois », « Jamais relancé »). Filtres par nombre de relances, mise à jour toute seule toutes les 5 secondes.
- **Règles** : seuls les invités dont l'invitation est envoyée et qui n'ont pas répondu sont relancés. Dès qu'un invité répond (présent, absent ou peut-être), il sort de la liste et n'est plus jamais relancé. Au plus **3 relances** par invité, même à la main. Pas de relance pour un événement passé, annulé ou en brouillon. Un second clic dans les 10 minutes sur le même invité est refusé (double clic).
- **Canaux** : le même que l'invitation (WhatsApp ou e-mail), jamais de SMS ; si le contact manque, l'autre canal est utilisé, et sans aucun contact l'invité est signalé. Le message est écrit dans la langue de l'invité, avec son lien personnel (`?lang=`), qui ouvre la page de réponse sans connexion.
- **En un clic** : « Relancer » sur une ligne. Pour un invité WhatsApp, WhatsApp s'ouvre avec le message prêt (le message part depuis le téléphone de l'administrateur) et la relance est notée dans le journal `Reminder` ; pour un invité e-mail, le serveur envoie l'e-mail (`reply_to` = `CONTACT_EMAIL`). « Envoyer maintenant · N » envoie tous les e-mails à échéance d'un coup et indique combien de relances WhatsApp restent à faire une par une (WhatsApp ne permet pas l'envoi automatique).
- **Réglages par événement** : première relance 3, 7 ou 14 jours après l'invitation ; puis tous les 3, 7 ou 14 jours ; 1, 2 ou 3 relances au maximum ; heure d'envoi ; envoi automatique des e-mails (désactivé par défaut).
- **Envoi automatique** : lancez `python manage.py send_reminders` une fois par heure (cron, tâche planifiée Windows, planificateur de l'hébergeur). La commande envoie les e-mails à échéance des événements qui ont activé l'envoi automatique, à partir de leur heure d'envoi. Options : `--dry-run` (affiche sans envoyer), `--event <numéro>`, `--any-hour`. Elle construit les liens avec `SITE_URL` (variable du `.env`, par exemple `https://eventlead.ht`).
- **E-mails réels** : tant que `EMAIL_BACKEND` est celui par défaut (console), les e-mails s'affichent dans le terminal du serveur au lieu de partir, et la page l'indique. Configurez `EMAIL_*` dans le `.env` pour les envoyer vraiment.
- Après un `git pull` : `python manage.py migrate`, puis `python manage.py seed_demo --reset` si vous voulez des données neuves (un invité du mariage y a déjà reçu une relance).

## Contribution en argent

- **Réglage par événement** : la case « accepter les contributions en argent » du formulaire de l'événement (désactivée par défaut). Elle peut s'ajouter à une liste de cadeaux ou la remplacer : sans liste de cadeaux, l'invité qui confirme sa présence voit seulement « Souhaitez-vous faire une contribution ? » (Contribuer en argent / Non merci, continuer).
- **Côté invité** (lien personnel, sans compte) : après avoir confirmé sa présence, l'invité choisit « Je préfère contribuer en argent » au lieu d'un cadeau. La page propose 1 000, 2 500, 5 000, 10 000 ou 25 000 HTG, ou « Autre montant » (de 500 à 500 000 HTG), avec l'équivalent en dollars (taux fixe, 5 000 HTG = 37,50 USD), le choix MonCash ou NatCash, un petit mot facultatif (300 signes) et la mention « Seuls les hôtes voient votre nom et votre montant ». « Je préfère choisir un cadeau » ramène à la liste.
- **Paiement et réponse en une seule étape** : le bouton « Contribuer N HTG » ouvre la fenêtre de paiement déjà sur le bon mode. Si le paiement est accepté, la réponse de l'invité est confirmée (présent, sans cadeau) et devient définitive ; s'il est refusé (mauvais code, par exemple), la fenêtre se rouvre avec le motif, rien n'est confirmé et l'invité peut réessayer. Un invité qui a déjà répondu n'est jamais débité une seconde fois. Stripe et PayPal ne sont pas proposés ici.
- **Côté équipe** : sur la page de l'événement, la carte « Contributions en argent » (mise à jour toute seule) donne le total, puis pour chaque contribution l'invité, le montant, le mode, la référence, le petit mot et la date. Les autres invités ne voient jamais ni nom, ni montant, ni message. Un invité qui a contribué, et un événement qui a des contributions, ne peuvent pas être supprimés.
- **Modèle** : `payments.Contribution` (un invité, un paiement `Payment` de type `contribution`, un montant et le petit mot). Paiements en mode démo comme partout : MonCash code `123456`, NatCash PIN à 4 chiffres.
- Après un `git pull` : `python manage.py migrate` (deux migrations : `events.0007`, `payments.0002`), puis `python manage.py seed_demo --reset` si vous voulez des données neuves (le mariage de démonstration accepte les contributions et un invité y a déjà contribué 5 000 HTG).

## Remerciements et album photo

- **Côté équipe** : page « Remerciements » (`/admin-dashboard/remerciements/`, lien dans le menu et bouton sur la page de l'événement) : choisissez l'événement. Vous y écrivez le message de remerciement (600 signes au plus, un texte par défaut sinon), ajoutez ou supprimez des photos, puis cliquez sur « Publier les remerciements ». Tant que ce n'est pas publié, les invités ne voient rien ; « Ne plus publier » referme tout.
- **Côté invité** (lien personnel, sans compte) : une fois publié, l'invité qui a **confirmé sa présence** ouvre `/invitation/<jeton>/remerciements/` (bouton « Voir les remerciements et l'album » sur sa page de réponse, ou lien envoyé par WhatsApp ou e-mail). Il y trouve le message des hôtes, l'album (6 photos, la dernière porte « +N » et déplie le reste ; clic = visionneuse plein écran, flèches et Échap au clavier), un mot de remerciement personnel (« Nadège, merci pour votre cadeau : Panier de fruits. » ou, pour une contribution, un merci sans montant), « Télécharger l'album » (un seul fichier `.zip`) et « Ajouter mes photos ». Les invités qui n'ont pas confirmé (en attente, absent, peut-être) n'ont accès à rien.
- **Photos** : JPEG, PNG ou WebP, 12 Mo au plus chacune, 20 à la fois, 30 par invité, 500 par album. Chaque photo est vérifiée avec Pillow (un faux fichier `.jpg` est refusé sans bloquer les autres), tournée dans le bon sens, réduite à 2 400 pixels, privée de ses données de position (GPS) et enregistrée en JPEG avec une miniature de 640 pixels. Les noms de fichiers sont tirés au hasard (`media/albums/<événement>/<hasard>.jpg`) : l'adresse d'une photo ne se devine pas. Supprimer une photo ou un événement supprime aussi les fichiers. L'équipe peut retirer n'importe quelle photo, avec le nom de l'invité qui l'a ajoutée.
- **Envoi** : sur la page de l'événement, chaque invité présent a son bouton « Envoyer », par le même canal que l'invitation, jamais par SMS. E-mail : le serveur l'envoie (comme les relances, `reply_to` = `CONTACT_EMAIL`). WhatsApp : WhatsApp s'ouvre avec le message prêt, dans la langue de l'invité, avec son lien personnel, et l'envoi est noté. « Envoyer par e-mail · N » envoie tous les e-mails d'un coup et indique combien de WhatsApp restent à faire. Un second clic dans les 10 minutes est refusé.
- **Fichiers en production** : les photos sont dans le dossier `media/` (ignoré par git). Le serveur de développement le sert tout seul ; en production, faites servir `MEDIA_URL` par le serveur web et sauvegardez ce dossier.
- Après un `git pull` : `python manage.py migrate` (`events.0008`), puis `python manage.py seed_demo --reset` si vous voulez des données neuves (l'anniversaire passé a des remerciements publiés, 8 photos et un cadeau réservé par Nadège).

## Tuiles « Pour chaque occasion » et police

- **Tuiles** : dans la section Services de l'accueil, une tuile par catégorie d'événement (photo dans un cadre arrondi, bande violette avec le nom, filet doré). Elles suivent la liste des catégories : ajouter, renommer ou réordonner une catégorie dans **Admin > Catégories** change l'accueil. Une tuile mène à `/evenements/?categorie=<identifiant>` quand la catégorie a un événement public à venir, sinon au formulaire de contact.
- **Photo de chaque tuile** : **Admin > Catégories > Modifier > Photo de la tuile** (JPEG, PNG ou WebP, 12 Mo au plus, 480 x 360 pixels au minimum). Le site la recadre en 4:3 et la réduit à 960 x 720 (JPEG). Remplacer ou cocher « Retirer la photo » supprime l'ancien fichier. Sans photo, la tuile affiche un décor violet provisoire avec l'icône dorée de la catégorie. Un prompt Gemini par catégorie se trouve dans `docs/prompts-gemini-categories.md`.
- **Catégories par défaut** : Anniversaire, Mariage, Baby shower, Baptême, Gala, Conférence, Concert (`DEFAULT_CATEGORIES` dans `events/models.py`). Le bouton **Ajouter les catégories par défaut** (Admin > Catégories) crée celles qui manquent sans toucher aux autres ; `seed_demo --reset` les recrée aussi.
- **Police** : Old Standard TT (Google Fonts, graisses 400 et 700) pour les titres et les chiffres, Jost pour le texte. Pour la changer, modifiez la variable `--font-display` en haut de `static/css/eventlead.css` **et** le lien Google Fonts de `templates/base.html` (`templates/dashboard/seating/print.html` nomme aussi la police du plan de table imprimé). Cette police n'a que deux graisses : les titres sont en 400, les chiffres et sceaux en 700, et `font-synthesis-weight: none` évite un faux gras.
- Après un `git pull` : `python manage.py migrate` (`events.0009`, champ photo), puis cliquez sur **Ajouter les catégories par défaut** (ou `python manage.py seed_demo --reset` pour des données neuves).

## Envoi des invitations (V1)

Chaque invité possède un `magic_token`. Dans `/admin-dashboard/invites/`, l'admin ouvre WhatsApp (`wa.me`) ou son client e-mail (`mailto:`) avec un message prérempli, dans la langue de l'invité, contenant le lien, ou copie le lien, puis marque l'invitation comme envoyée.

## Tests

```bash
python manage.py test
```

302 tests couvrent la règle « dernière unité », la transaction annulée en cas de conflit, le caractère définitif des réponses, le parcours invité complet jusqu'à la publicité puis l'accueil, le défilé de l'accueil, les redirections après connexion, les règles d'accès par rôle, le paiement VIP et l'affichage de chaque page principale, l'absence de connexion forcée sur le parcours invité et la page d'accueil publique, les catégories d'événements (gestion réservée à l'administrateur, filtre, badge, événements privés jamais exposés) l'espace d'aide (page, bouton WhatsApp, formulaire, statuts, export CSV, aides du parcours) le QR code d'entrée et le pointage (codes uniques, billet réservé aux présents, validation une seule fois, refus des codes inconnus ou d'un autre événement, ajout sur place, annulation, chiffres) les relances (qui est à relancer et quand, arrêt à la réponse, maximum de 3, e-mail dans la langue de l'invité, WhatsApp seulement noté, jamais de SMS, réglages, commande planifiée) le plan de table (places et accompagnants, déplacement, tables, placement automatique, numéro sur le billet et au pointage) la contribution en argent (montants, MonCash et NatCash seulement, paiement refusé sans réponse enregistrée, jamais de double débit, montants jamais montrés aux autres invités, carte réservée à l'équipe) les remerciements et l'album (photos vérifiées, réduites et sans données GPS, limites, page réservée aux invités présents et à partir de la publication, merci personnel, téléchargement .zip, envoi WhatsApp ou e-mail sans double envoi, fichiers supprimés avec la photo) et les trois langues (sélecteur, cookie, profil, `?lang=`, pages principales en anglais et en créole sans reste de français, message d'invitation par langue, catalogues complets).

## Production

- `DEBUG=False`, `SECRET_KEY`, `ALLOWED_HOSTS` et `DATABASE_URL` (PostgreSQL) dans l'environnement.
- `python manage.py collectstatic`, servir `staticfiles/` (WhiteNoise ou serveur web).
- Médias : définir `DEFAULT_FILE_STORAGE_BACKEND` (S3 via `django-storages`, ou Cloudinary) et installer le paquet correspondant.
- La photo en arche du haut de page, `static/img/photos/hero-arch.jpg` (portrait, environ 4/5, sans texte par-dessus), est une image générée par IA et fournie par le client (FAYaFA_Tech), simplement compressée en JPEG ; elle reçoit un léger voile violet en CSS. Remplacez ce fichier pour changer de photo. Les photos d'ambiance (`static/img/photos/`) sont des visuels de remplacement : remplacez-les par les photos du client (couvertures d'événements via l'admin, images de l'accueil dans `templates/core/landing.html`). Les polices sont chargées depuis Google Fonts. Police : les titres et les chiffres utilisent **Playfair Display** (traits plus épais que Bodoni Moda, donc lisible même sur les montants comme « 5 000 HTG »), le texte courant Jost. Pour en changer, modifiez deux endroits seulement : la variable `--font-display` au début de `static/css/eventlead.css` et le lien Google Fonts de `templates/base.html` (si la nouvelle police n'a qu'une graisse, ajoutez `font-synthesis: none`). Playfair Display affiche par défaut des chiffres « elzévir » : `html { font-feature-settings: "lnum" }` (fin du fichier CSS) les aligne. Les titres sont en graisse 500 (les petits titres en 600) et les montants et chiffres clés ont la classe `.fig` (graisse 600, espace insécable dans « 5 000 HTG »). Les petits textes de l'accueil (étiquettes, dates, adresses, pied de page) ont au moins 13 à 15 px. Les photos des services sont dans `SERVICES` (`core/views.py`), fichiers `static/img/photos/svc-*.jpg` (des recadrages des deux photos fournies : remplacez-les par vos propres photos, 720 x 480).
