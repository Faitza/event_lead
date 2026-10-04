"""Album photo partagé d'un événement : envoi contrôlé, miniatures, téléchargement en .zip."""
import io
import os
import tempfile
import zipfile

from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import AlbumPhoto

MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_REQUEST_BYTES = 120 * 1024 * 1024
MAX_PER_UPLOAD = 20
MAX_PER_GUEST = 30
MAX_PER_EVENT = 500
MAX_PIXELS = 50_000_000
FULL_SIDE = 2400
THUMB_SIDE = 640
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class AlbumError(Exception):
    """Une photo refusée : le message est écrit pour la personne qui l'envoie."""


def _flatten(image):
    """Image en RGB ; une transparence est posée sur fond blanc."""
    if image.mode == "RGB":
        return image
    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, (255, 255, 255))
    background.paste(rgba, mask=rgba.split()[-1])
    return background


def _encode(image, side, quality):
    """Image réduite à `side` pixels au plus, en JPEG sans métadonnées (donc sans position GPS)."""
    copy = _flatten(image.copy())
    copy.thumbnail((side, side), Image.LANCZOS)
    buffer = io.BytesIO()
    copy.save(buffer, "JPEG", quality=quality, optimize=True)
    return ContentFile(buffer.getvalue(), name="photo.jpg")


def _load_checked(uploaded):
    """Ouvre une photo envoyée après vérification (poids, format, taille). Lève AlbumError si elle est refusée."""
    name = getattr(uploaded, "name", "") or ""
    if uploaded.size > MAX_FILE_BYTES:
        raise AlbumError(_("« %(name)s » est trop lourde (12 Mo au plus).") % {"name": name})
    invalid = _("« %(name)s » n'est pas une photo valide (JPEG, PNG ou WebP).") % {"name": name}
    try:
        probe = Image.open(uploaded)
        probe.verify()
        uploaded.seek(0)
        image = Image.open(uploaded)
        if image.format not in ALLOWED_FORMATS:
            raise AlbumError(invalid)
        if image.width * image.height > MAX_PIXELS:
            raise AlbumError(_("« %(name)s » est trop grande (50 millions de pixels au plus).") % {"name": name})
        image = ImageOps.exif_transpose(image)
        image.load()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise AlbumError(invalid)
    return image


def prepare(uploaded):
    """Vérifie une photo envoyée et renvoie (grande version, miniature). Lève AlbumError si elle est refusée."""
    image = _load_checked(uploaded)
    return _encode(image, FULL_SIDE, 86), _encode(image, THUMB_SIDE, 80)


TILE_SIZE = (960, 720)  # tuiles « Pour chaque occasion » de l'accueil : 4/3
TILE_MIN = (480, 360)


def tile_photo(uploaded):
    """Photo d'une tuile de l'accueil : vérifiée, recadrée au centre en 4/3, en JPEG sans métadonnées."""
    image = _load_checked(uploaded)
    if image.width < TILE_MIN[0] or image.height < TILE_MIN[1]:
        raise AlbumError(_("Cette photo est trop petite : %(w)d x %(h)d pixels au moins.") % {"w": TILE_MIN[0], "h": TILE_MIN[1]})
    fitted = ImageOps.fit(_flatten(image), TILE_SIZE, Image.LANCZOS, centering=(0.5, 0.4))
    buffer = io.BytesIO()
    fitted.save(buffer, "JPEG", quality=86, optimize=True)
    return ContentFile(buffer.getvalue(), name="tuile.jpg")


def add_photos(event, files, guest=None):
    """Ajoute les photos reçues ; une photo refusée n'empêche pas les autres. Renvoie (nombre ajouté, erreurs)."""
    added, errors = 0, []
    files = list(files)
    if not files:
        return 0, [_("Choisissez au moins une photo.")]
    if len(files) > MAX_PER_UPLOAD:
        errors.append(
            ngettext("%(n)d photo à la fois au plus.", "%(n)d photos à la fois au plus.", MAX_PER_UPLOAD) % {"n": MAX_PER_UPLOAD}
        )
        files = files[:MAX_PER_UPLOAD]
    for uploaded in files:
        if AlbumPhoto.objects.filter(event=event).count() >= MAX_PER_EVENT:
            errors.append(_("L'album est complet."))
            break
        if guest is not None and AlbumPhoto.objects.filter(event=event, guest=guest).count() >= MAX_PER_GUEST:
            errors.append(
                ngettext("Vous pouvez ajouter %(n)d photo au plus.", "Vous pouvez ajouter %(n)d photos au plus.", MAX_PER_GUEST)
                % {"n": MAX_PER_GUEST}
            )
            break
        try:
            full, thumb = prepare(uploaded)
        except AlbumError as error:
            errors.append(str(error))
            continue
        photo = AlbumPhoto(event=event, guest=guest)
        photo.image.save("photo.jpg", full, save=False)
        photo.thumb.save("miniature.jpg", thumb, save=False)
        photo.save()
        added += 1
    return added, errors


def build_zip(event):
    """Toutes les photos de l'événement dans un fichier .zip temporaire (rendu au début, prêt à être envoyé)."""
    archive = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as zf:  # les JPEG sont déjà compressés
        for number, photo in enumerate(event.photos.all(), start=1):
            if not photo.image:
                continue
            with photo.image.open("rb") as source:
                zf.writestr(f"photo-{number:03d}{os.path.splitext(photo.image.name)[1] or '.jpg'}", source.read())
    archive.seek(0)
    return archive
