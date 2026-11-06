# 20 choses à vérifier avant de lancer le site

Vérifié le 6 octobre 2026. Les tests sont dans `core/test_lancement.py`.

| # | Point | État | Où |
|---|-------|------|----|
| 1 | Page RGPD (confidentialité) | Déjà là, complétée (compteur de visites) | `/confidentialite/`, fr / en / ht |
| 2 | Page de CGU | Déjà là | `/conditions-utilisation/` |
| 3 | Clés d'API hors du navigateur | Déjà bon : toutes les clés (MonCash, Google, PayPal, e-mail) sont dans `.env`, côté serveur ; aucune clé dans `static/js/` | `.env.example` |
| 4 | HTTPS obligatoire | **Ajouté** : en ligne (`DEBUG=False`), http:// renvoie vers https://, HSTS 1 an, cookies en https:// seulement | `eventlead/settings.py` |
| 5 | Bannière cookies | Déjà là (le site n'utilise que des cookies nécessaires) | `partials/_cookie_note.html` |
| 6 | Meta title et description | Déjà là ; chaque page publique a son propre titre (testé) | `base.html` |
| 7 | Image pour les réseaux | **Ajoutée** : `static/img/partage.jpg` (1200 x 630), balises Open Graph et X ; une fiche d'événement partage son titre et sa photo | `base.html`, `events/public_detail.html` |
| 8 | Favicon | Déjà là | `static/favicon.ico`, `static/img/favicon*.png` |
| 9 | Sitemap et robots.txt | **Ajoutés** : `/sitemap.xml` (pages publiques + événements publics à venir) et `/robots.txt` ; les pages privées ont aussi `noindex` | `core/seo.py` |
| 10 | Texte des images (alt) | Déjà là : toutes les images ont un `alt` (vide pour les photos de décor) ; vérifié par le test des liens | |
| 11 | Images compressées | Déjà là pour les envois (`core/uploads.py`) ; **logo allégé** (1 Mo à 400 Ko pour les 12 fichiers) | `static/img/logo/` |
| 12 | Vitesse des pages | Déjà bon : fichiers compressés et mis en cache (WhiteNoise), images en chargement différé, cache du contenu | `docs/solidite.md` |
| 13 | Contraste | Déjà vérifié (passe de lisibilité) | |
| 14 | Site responsive | Déjà là (téléphone, tablette, ordinateur) | |
| 15 | Page 404 personnalisée | Déjà là (404, 403, 429, 500) | `templates/errors/` |
| 16 | Liens cassés | **Test ajouté** : il suit tous les liens internes des pages publiques, visiteur et connecté | `core/test_lancement.py` |
| 17 | Validation des formulaires | Déjà là ; **limite de longueur** ajoutée aux messages de contact et aux avis | `core/forms.py` |
| 18 | Anti-spam | Limite de requêtes déjà là ; **champ piège** ajouté sur contact, avis et inscription (il était seulement sur l'aide) | `core/forms.py`, `accounts/forms.py` |
| 19 | Outil d'analytics | **Ajouté, privé** : compteur de pages vues par jour, sans cookie ni adresse IP, sans Google Analytics ; dans Tableau de bord > Provenance des visites, avec les liens utm_ | `core/visits.py` |
| 20 | Un seul bouton principal | Déjà bon : un seul bouton doré par écran (« Organiser mon événement » en haut de l'accueil), les autres sont en contour | `core/landing.html` |

## En ligne

- Le domaine doit avoir son certificat https **avant** de mettre `DEBUG=False` (sinon le navigateur retient https:// pour un site qui ne l'a pas encore). En attendant, mettre `SECURE_HSTS_SECONDS=0` dans `.env`.
- `python manage.py check --deploy` ne signale plus que deux choix volontaires : HSTS pour les sous-domaines et la liste « preload », laissés éteints.
- Après la mise en ligne, déclarer `https://votre-domaine/sitemap.xml` dans Google Search Console.
