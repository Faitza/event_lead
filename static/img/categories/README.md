# Photos par défaut des tuiles « Pour chaque occasion »

Un fichier par catégorie, nommé avec l'identifiant de la catégorie : `anniversaire.jpg`, `mariage.jpg`,
`baby-shower.jpg`, `bapteme.jpg`, `gala.jpg`, `conference.jpg`, `concert.jpg`.

- Format paysage 4:3, JPEG, 960 x 720 pixels (la commande ci-dessous s'en charge).
- Une photo ajoutée dans **Admin > Catégories > Modifier** passe toujours avant celle de ce dossier.
- Ajouter ou remplacer une photo ici : `python tools/set_category_photo.py mariage chemin/vers/photo.jpg --licence Pexels --source <adresse de la photo> --author "<nom>"`
  (recadre en 4:3 et note la photo dans `docs/credits-photos.md`).
