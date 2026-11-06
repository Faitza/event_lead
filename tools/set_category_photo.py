#!/usr/bin/env python3
"""Installe la photo par défaut d'une catégorie et la note dans docs/credits-photos.md.

  python tools/set_category_photo.py mariage C:\\Users\\moi\\Downloads\\photo.jpg \\
      --licence Pexels --source https://www.pexels.com/photo/... --author "Nom du photographe"

La photo est recadrée en 4:3 (960 x 720 au plus, JPEG) et enregistrée dans static/img/categories/<identifiant>.jpg.
Jamais agrandie : une petite photo garde sa taille (480 x 360 au minimum).
Les identifiants par défaut : anniversaire, mariage, baby-shower, bapteme, remise-de-diplome, gala, conference, concert.

Si le recadrage au centre coupe le sujet, donnez le point à garder : --focus 0.5,0.8 (gauche-droite, haut-bas ;
0 = bord gauche ou haut de la photo, 1 = bord droit ou bas), et --zoom 1.5 pour un cadre plus serré
(1 = le plus grand cadre possible). La photo d'origine n'est pas modifiée.
Licences acceptées pour une photo trouvée en ligne : Pexels, Unsplash, Pixabay, CC0 (licences gratuites,
sans obligation de crédit, mais on note quand même la source). Pour vos propres photos ou des images faites
par IA : --licence "Photo du client" ou --licence "Image IA fournie par le client".
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "static" / "img" / "categories"
CREDITS = ROOT / "docs" / "credits-photos.md"
SIZE = (960, 720)
MIN_SIZE = (480, 360)
HEADER = (
    "# Crédits des photos\n\n"
    "Photos ajoutées à la main (tuiles « Pour chaque occasion »). Les photos des événements, des services et de "
    "l'accueil du jeu de démonstration (`static/img/photos/`) sont des visuels de remplacement fournis par le client ou "
    "générés par IA : voir le README.\n\n"
    "| Fichier | Licence | Auteur | Source | Date |\n|---|---|---|---|---|\n"
)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("slug", help="identifiant de la catégorie (ex. mariage, baby-shower)")
    parser.add_argument("photo", help="fichier image à installer (JPEG, PNG ou WebP)")
    parser.add_argument("--licence", required=True, help="Pexels, Unsplash, Pixabay, CC0, « Photo du client »...")
    parser.add_argument("--source", default="", help="adresse de la page de la photo")
    parser.add_argument("--author", default="", help="nom du photographe")
    parser.add_argument("--focus", default="0.5,0.4", help="point à garder dans le cadre, ex. 0.5,0.8 (défaut : 0.5,0.4)")
    parser.add_argument("--zoom", type=float, default=1.0, help="1 = le plus grand cadre possible, 1.5 = cadre plus serré (défaut : 1)")
    parser.add_argument("--note", default="", help="remarque à noter dans le fichier des crédits (ex. filigrane, marque visible)")
    args = parser.parse_args()

    slug = args.slug.strip().lower()
    if not re.fullmatch(r"[a-z0-9-]+", slug):
        sys.exit("Identifiant invalide : lettres minuscules, chiffres et tirets seulement (ex. baby-shower).")
    src = Path(args.photo)
    if not src.is_file():
        sys.exit("Fichier introuvable : %s" % src)
    try:
        with Image.open(src) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
    except Exception as exc:  # noqa: BLE001 - message simple pour l'utilisateur
        sys.exit("Ce fichier n'est pas une image lisible : %s" % exc)
    if image.width < MIN_SIZE[0] or image.height < MIN_SIZE[1]:
        sys.exit("Photo trop petite : %d x %d pixels, il en faut au moins %d x %d." % (image.width, image.height, *MIN_SIZE))

    try:
        focus = tuple(min(1.0, max(0.0, float(part))) for part in args.focus.split(","))
        if len(focus) != 2:
            raise ValueError
    except ValueError:
        sys.exit("--focus doit avoir la forme 0.5,0.8 (deux nombres entre 0 et 1).")

    # Plus grand cadre 4:3 possible dans la photo, placé autour du point à garder ; réduit à 960 x 720 si besoin, jamais agrandi.
    ratio = SIZE[0] / SIZE[1]
    if image.width / image.height > ratio:
        crop_w, crop_h = round(image.height * ratio), image.height
    else:
        crop_w, crop_h = image.width, round(image.width / ratio)
    if not 1.0 <= args.zoom <= 4.0:
        sys.exit("--zoom doit être compris entre 1 et 4.")
    crop_w, crop_h = round(crop_w / args.zoom), round(crop_h / args.zoom)
    left, top = round((image.width - crop_w) * focus[0]), round((image.height - crop_h) * focus[1])
    tile = image.crop((left, top, left + crop_w, top + crop_h))
    if tile.width > SIZE[0]:
        tile = tile.resize(SIZE, Image.LANCZOS)
    if tile.width < MIN_SIZE[0] or tile.height < MIN_SIZE[1]:
        sys.exit("Après recadrage en 4:3, la photo ferait %d x %d pixels : il en faut au moins %d x %d." % (*tile.size, *MIN_SIZE))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUT_DIR / ("%s.jpg" % slug)
    tile.save(target, "JPEG", quality=86, optimize=True, progressive=True)

    name = "static/img/categories/%s.jpg" % slug
    licence = "%s (%s)" % (args.licence, args.note) if args.note else args.licence
    row = "| `%s` | %s | %s | %s | %s |" % (name, licence, args.author or "-", args.source or "-", date.today().isoformat())
    CREDITS.parent.mkdir(parents=True, exist_ok=True)
    text = CREDITS.read_text(encoding="utf-8") if CREDITS.exists() else HEADER
    lines = [line for line in text.rstrip("\n").split("\n") if not line.startswith("| `%s`" % name)]
    CREDITS.write_text("\n".join(lines + [row]) + "\n", encoding="utf-8")
    print("Photo installée : %s (%d x %d)\nCrédit noté dans %s" % (target.relative_to(ROOT), *tile.size, CREDITS.relative_to(ROOT)))


if __name__ == "__main__":
    main()
