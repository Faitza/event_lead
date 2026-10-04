# Solidité du site : les 20 points

Ce qui est fait dans le code, où ça se trouve, et ce qu'il reste à faire soi-même au moment de la mise en ligne.
Les réglages se changent dans le fichier `.env` (voir `.env.example`), sans toucher au code.

Légende : **Fait** = rien à faire. **Fait + 1 étape** = le code est prêt, une action est à faire chez l'hébergeur ou un fournisseur.

| # | Point | État | Où |
|---|---|---|---|
| 01 | Limiter le nombre de requêtes par visiteur | Fait | `core/ratelimit.py` |
| 02 | Plafonner les appels d'API | Fait | `core/quotas.py`, `events/geocoding.py` |
| 03 | Plafonner les dépenses chez les fournisseurs | Pas encore d'objet + étapes | ci-dessous |
| 04 | Message quand ça plante | Fait | `templates/errors/500.html`, `400.html`, `429.html` |
| 05 | Chargement au lieu d'un écran blanc | Fait | `static/js/eventlead.js`, `static/css/solidite.css` |
| 06 | Cas où il n'y a rien à afficher | Fait (déjà présent) | chaque liste a son message « Aucun ... » |
| 07 | Requêtes qui échouent | Fait | `static/js/eventlead.js` |
| 08 | API qui ne répondent pas | Fait | délais : carte 5 s, e-mail 15 s, navigateur 20 s, paiement |
| 09 | Double clic sur « envoyer » | Fait | `static/js/eventlead.js` |
| 10 | Double paiement | Fait | `payments/idempotency.py` |
| 11 | Charger seulement ce qui est affiché | Fait | listes découpées, portail organisateur |
| 12 | Index pour accélérer les recherches | Fait | migrations `*_index_recherches` |
| 13 | Longues listes découpées en pages | Fait | `core/paging.py`, `templates/partials/_pagination.html` |
| 14 | Compresser les fichiers envoyés | Fait | `core/uploads.py`, WhiteNoise |
| 15 | Limiter le poids des fichiers envoyés | Fait | `core/uploads.py`, `settings.py` |
| 16 | Garder en mémoire ce qui ne change pas | Fait | `core/content_cache.py` |
| 17 | Être alerté si le site tombe | Fait + 1 étape | adresse `/sante/` + UptimeRobot |
| 18 | Garder une trace de chaque erreur | Fait + 1 étape | `logs/eventlead.log` + e-mail (`ADMINS`) |
| 19 | Tester avec plusieurs visiteurs | Fait | `tools/charge.py` |
| 20 | Vérifier que la sauvegarde se restaure | Fait + 1 étape | `sauvegarder`, `verifier_sauvegarde` |

## Le détail, point par point

**01. Limite de requêtes.** Chaque visiteur (adresse IP) a droit à 240 pages par minute, dont 40 formulaires envoyés.
Les pages sensibles ont leur propre plafond : connexion 10 essais en 5 min, inscription 6 par heure, contact / avis /
aide 5 en 10 min, paiement et contribution 10 en 10 min, codes d'entrée 30 en 10 min (empêche de deviner les codes),
photos de l'album 10 envois en 10 min. Au-delà, une page « Un peu de patience » s'affiche. L'équipe connectée en
administrateur n'est jamais limitée (le jour J, plusieurs personnes pointent depuis le même Wi-Fi).

**02. Plafond d'appels.** Carte (OpenStreetMap) : 500 recherches d'adresse par jour, et chaque adresse trouvée est
gardée 30 jours. E-mails : 280 par jour (relances et remerciements). Au-delà, l'écran le dit (« partira demain »)
et le journal garde une trace. Réglages : `GEOCODER_DAILY_LIMIT`, `EMAIL_DAILY_LIMIT`.

**03. Dépenses chez les fournisseurs.** Aujourd'hui le site n'appelle aucun service payant au volume : la carte et la
connexion Google sont gratuites, les paiements sont en mode démo, et MonCash / NatCash prennent une commission sur
l'argent reçu (ils ne facturent pas d'appels). Quand vous prendrez un service payant :
1. E-mails (par exemple Brevo, 300 e-mails gratuits par jour) : restez sur l'offre gratuite ou une offre à prix fixe,
   sans paiement « à l'usage », et mettez `EMAIL_DAILY_LIMIT` un peu en dessous de la limite de l'offre.
2. Hébergement : choisissez un forfait à prix fixe par mois (PythonAnywhere l'est).
3. Tout service qui demande une carte bancaire : activez l'alerte de budget et le plafond de dépense dans son espace
   « Facturation » avant la première utilisation.

**04. Message quand ça plante.** Une erreur du serveur affiche « Un problème est survenu » avec « Réessayer », le
retour à l'accueil et le lien WhatsApp, au lieu d'une page blanche. Cette page n'utilise pas la base de données, donc
elle s'affiche même si la base est en panne. Fichier trop lourd : page « Demande refusée ».

**05. Chargement.** Une fine barre dorée apparaît en haut de l'écran quand la page suivante tarde, et le bouton
cliqué montre un petit cercle qui tourne.

**06. Rien à afficher.** Déjà en place avant ce travail : chaque liste vide affiche un message (« Aucun invité
trouvé. », « Aucune transaction. », etc.). Vérifié sur toutes les listes.

**07 et 08. Réseau et services lents.** Les mises à jour en direct (suivi des réponses, pointage, plan de table,
cadeaux) ont 20 secondes pour répondre. Si le réseau coupe ou si le serveur répond mal, un bandeau
« La connexion a échoué... » s'affiche en bas, puis « Connexion rétablie. » quand ça revient. Côté serveur :
la carte a 5 s, le serveur d'e-mail 15 s, et un service de paiement en panne donne « Le service de paiement ne
répond pas. Aucun montant n'a été débité. » au lieu d'un plantage.

**09. Double clic.** Un formulaire envoyé ne peut pas repartir une deuxième fois : le bouton devient inactif. Si la
page ne change pas (téléchargement, réseau coupé), il redevient cliquable au bout de 15 secondes.

**10. Double paiement.** Chaque formulaire de paiement porte un numéro unique. Le paiement est d'abord enregistré
« en attente » avec ce numéro (la base refuse un deuxième paiement avec le même numéro), puis seulement débité.
Un double clic, une page rechargée ou un réseau qui renvoie la demande retrouvent donc le premier paiement :
« Ce paiement a déjà été effectué : rien n'a été débité une deuxième fois. » Valable pour les billets, l'accès VIP
et les contributions en argent.

**11. Données chargées.** Les listes ne lisent que la page affichée. Le portail organisateur lisait l'invitation
événement par événement : une seule lecture maintenant, quel que soit le nombre d'événements.

**12. Index.** Ajoutés sur ce qu'on cherche le plus : événements publics à venir, invités par événement et par
statut, dernières réponses, e-mail des invités, paiements par statut et par date, demandes d'aide, messages, avis,
publicités actives, pointages.

**13. Pages.** Invités 50 par page, paiements 50, événements 25, publicités 25, demandes d'aide 30, messages 30,
événements publics 12, billetterie 12. Les filtres (événement, statut, recherche) sont gardés d'une page à l'autre.

**14. Compression.** Photo de couverture, image de publicité et photo de profil : vérifiées, tournées dans le bon
sens, réduites (1920, 1600 et 512 pixels), débarrassées de leurs métadonnées (dont la position GPS) et
réenregistrées en JPEG. Une photo de téléphone de 5 Mo pèse ensuite quelques centaines de Ko. Un logo transparent
reste en PNG. Le CSS et le JavaScript sont envoyés compressés (WhiteNoise) : le CSS passe de 95 Ko à 19 Ko.

**15. Poids des envois.** Photo 12 Mo au plus, vidéo de couverture 40 Mo (MP4, WebM ou MOV), album 20 photos par
envoi, formulaire sans fichier 5 Mo, 25 fichiers par envoi.

**16. Mémoire.** L'accueil et le menu gardent 5 minutes les catégories, événements publics, publicités et avis :
l'accueil passe de 7 lectures de la base à 0. Toute modification (événement, catégorie, publicité, avis) efface
cette mémoire, donc elle se voit tout de suite. CSS, JavaScript et images gardés une journée par le navigateur.

**17. Alerte si le site tombe.** L'adresse `/sante/` répond « ok » si la base et le cache fonctionnent, sinon une
erreur 503. À faire une fois le site en ligne (5 minutes, gratuit) :
1. Créez un compte sur uptimerobot.com.
2. « Add New Monitor » : type HTTP(s), adresse `https://votre-domaine/sante/`, vérification toutes les 5 minutes.
3. Choisissez comment être prévenu : e-mail, et l'application mobile UptimeRobot pour une notification sur le téléphone.

**18. Trace des erreurs.** Chaque erreur (serveur, et JavaScript chez les visiteurs) est écrite dans
`logs/eventlead.log` (5 fichiers de 2 Mo gardés). À faire : dans `.env`, mettre `ADMINS=votre-adresse@exemple.com`
et configurer l'envoi d'e-mails : chaque erreur du serveur vous arrive alors par e-mail avec le détail.

**19. Plusieurs visiteurs.** `python tools/charge.py --visiteurs 20 --duree 30` simule des visiteurs simultanés.
Résultat sur le serveur de développement (un seul processus) avec 20 visiteurs pendant 30 s : 1 013 pages servies,
0 erreur, 95 % des pages en moins de 1,8 s. Avec la limite active, le même test reçoit bien des réponses 429.
En production, un hébergeur avec plusieurs processus et PostgreSQL fait beaucoup mieux ; SQLite attend
maintenant jusqu'à 20 s au lieu d'échouer quand plusieurs personnes écrivent en même temps.

**20. Sauvegarde qui se restaure.**
- `python manage.py sauvegarder` crée `backups/eventlead-AAAAMMJJ-HHMMSS.zip` (toutes les données + photos) et garde
  les 14 dernières.
- `python manage.py verifier_sauvegarde` restaure la plus récente dans une base temporaire à côté (la vraie base n'est
  jamais touchée), compare le nombre de lignes de chaque table et contrôle chaque photo, puis affiche
  « Sauvegarde valide » ou la liste des problèmes.
- À faire chez l'hébergeur : une tâche planifiée chaque nuit (PythonAnywhere : onglet « Tasks ») :
  `cd ~/event_lead && python manage.py sauvegarder && python manage.py verifier_sauvegarde`.
  Une fois par semaine, téléchargez le dernier fichier `.zip` sur votre ordinateur : une sauvegarde qui reste sur le
  même serveur disparaît avec lui.
- Restaurer pour de vrai sur une base vide : `python manage.py migrate`, puis
  `python manage.py loaddata data.json` (fichier extrait du .zip), puis copier le dossier `media/` du .zip.

## Réglages pour la mise en ligne (`.env`)

```
DEBUG=False
ADMINS=votre-adresse@exemple.com
REAL_IP_HEADER=HTTP_X_REAL_IP        # PythonAnywhere : adresse réelle du visiteur
CACHE_URL=dbcache://eventlead_cache  # puis : python manage.py createcachetable
```

Puis `python manage.py collectstatic` (fichiers statiques compressés) et `python manage.py migrate`.
