# Petits détails du site (6 octobre 2026)

Vérification de la liste de 20 détails envoyée par le client, et ce qui a été ajouté.
Fichiers : `static/css/details.css`, `static/js/details.js`, `core/search.py`, `core/utm.py`, `templates/core/search.html`,
`templates/dashboard/utm/report.html`, `templates/partials/_cookie_note.html`, `templates/partials/_theme_toggle.html`.
Tests : `core/test_details.py`.

| N° | Détail | Où |
|---|---|---|
| 01 | Bouton mode sombre | Lune / soleil dans la barre du site et du tableau de bord. Le site reste clair par défaut : le mode sombre ne s'active que si le visiteur appuie, et le choix est gardé dans son navigateur (`localStorage`, clé `el-theme`). Le logo reste sur fond blanc. |
| 02 | Bandeau cookies simple | Petite carte en bas à gauche, une seule fois. Le site n'a que des cookies nécessaires (session, protection des formulaires, langue) : le bandeau informe, il ne demande pas de choix. Lien vers `/confidentialite/`. |
| 03 | Recherche sur tout le site | Loupe dans la barre, page `/recherche/?q=` : événements publics à venir, catégories, questions de l'aide, pages. Sans accents ni majuscules. Les événements privés n'apparaissent jamais. |
| 04 | Retour en haut | Bouton violet en bas à droite après 600 px de défilement, au-dessus du bouton WhatsApp. |
| 05 | Menu adapté au mobile | Déjà fait : menu repliable (bouton trois traits) sous 1200 px, barre latérale repliable dans le tableau de bord. |
| 06 | Animations de chargement | Déjà fait : barre dorée en haut pendant le chargement d'une page, petit cercle qui tourne dans le bouton d'un formulaire envoyé. |
| 07 | Effet au survol des boutons | Déjà fait : le bouton monte légèrement avec une ombre, couleur plus foncée. |
| 08 | Barre de progression au défilement | Fin filet doré en haut de l'écran, qui avance avec la lecture. |
| 09 | Bouton « copier » | Lien d'invitation (existant), adresse et lien d'un événement public, code d'entrée du billet, référence de paiement, lien de campagne. Attribut `data-copy="texte"`. |
| 10 | Version imprimable | Feuille d'impression pour tout le site (sans menu, pied de page ni boutons, noir sur blanc). Boutons « Imprimer » sur l'événement public, le billet, le reçu de paiement, l'aide (questions ouvertes à l'impression) et les pages légales ; plan de table imprimable (existant). Attribut `data-print`. |
| 11 | Menu qui reste en haut | Déjà fait : la barre du site reste collée en haut. |
| 12 | Lien « Aller au contenu » | Premier élément de chaque page, visible seulement au clavier (touche Tab). Va à la zone `#contenu`. |
| 13 | Oeil pour voir le mot de passe | Sur tous les champs mot de passe (connexion, inscription, PIN NatCash...). Le mot de passe repasse en points avant l'envoi. `data-no-eye` sur un champ pour l'exclure. |
| 14 | Tracking UTM des liens | Sans outil extérieur. Un lien avec `utm_source`, `utm_medium`, `utm_campaign` (et `utm_term`, `utm_content`) est gardé dans la session du visiteur ; s'il s'inscrit, paie, demande de l'aide ou écrit à l'équipe, une ligne est notée. Tableau de bord > **Provenance des visites** : totaux par source et campagne, dernières actions, et un générateur de lien à copier. |
| 15 | Message quand le formulaire passe | Déjà fait : message vert en haut à droite (contact, avis, inscription, profil, paiement...), page « demande envoyée » pour l'aide. |
| 16 | Message quand il échoue | Messages rouges existants (contact, avis, paiement), message ajouté sur l'aide, et pour tout formulaire refusé : message rouge en haut et curseur placé sur le premier champ à corriger. |
| 17 | Confirmation avant les actions importantes | Déjà fait pour supprimer (événement, invité, cadeau, catégorie, publicité, photo), annuler un pointage, envoyer des relances. Ajouté : publier ou retirer les remerciements, envoyer l'e-mail de remerciement à tous, marquer une publicité payée ou non payée. Attribut `data-confirm="Question ?"`. |
| 18 | Date de dernière mise à jour | Pages légales (existant, `LEGAL_UPDATED` dans `core/views.py`, passée au 6 octobre 2026) et page Aide (`HELP_UPDATED` dans `core/help.py`). |
| 19 | FAQ dépliable | Déjà fait : questions de `/aide/` qui s'ouvrent au clic, lien direct `/aide/#faq-<identifiant>`. |
| 20 | Bouton contact flottant | Déjà fait : bouton WhatsApp vert en bas à droite des pages publiques. |

Après mise à jour : `git pull`, `python manage.py migrate` (nouvelle table de provenance, `core/0005`), puis Ctrl+F5 dans le navigateur.
