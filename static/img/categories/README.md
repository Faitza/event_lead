# Photos par défaut des tuiles « Pour chaque occasion »

Un fichier par catégorie, nommé avec l'identifiant de la catégorie : `anniversaire.jpg`, `mariage.jpg`,
`baby-shower.jpg`, `bapteme.jpg`, `gala.jpg`, `conference.jpg`, `concert.jpg`, `remise-de-diplome.jpg`.

- Format paysage 4:3, JPEG, 960 x 720 pixels au plus (la commande ci-dessous s'en charge ; une petite photo garde sa taille, 480 x 360 au minimum).
- Une photo ajoutée dans **Admin > Catégories > Modifier** passe toujours avant celle de ce dossier.
- Ajouter ou remplacer une photo ici : `python tools/set_category_photo.py mariage chemin/vers/photo.jpg --licence Pexels --source <adresse de la photo> --author "<nom>"`
  (recadre en 4:3 et note la photo dans `docs/credits-photos.md`).
  Pour garder un sujet dans le cadre : `--focus 0.5,0.8` (gauche-droite, haut-bas, de 0 à 1) et `--zoom 1.5` pour un cadre plus serré.
- Les photos livrées ont été envoyées par le client : leurs droits restent à confirmer (voir `docs/credits-photos.md`).
