"""Fichiers envoyés par les utilisateurs : poids limité et photos compressées (points 14 et 15 de docs/solidite.md).

Une photo de téléphone pèse souvent 4 à 8 Mo. Elle est vérifiée, tournée dans le bon sens, réduite
(1920 pixels au plus pour une couverture, 512 pour un avatar), débarrassée de ses métadonnées (position GPS)
puis réenregistrée en JPEG : elle pèse alors quelques centaines de Ko, et les pages s'ouvrent plus vite.
Une image avec transparence (logo d'un partenaire) reste en PNG pour ne pas perdre son fond transparent.
"""
import io
import os
import struct

from django import forms
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext as _
from PIL import Image

from events.album import AlbumError, _load_checked

VIDEO_MAX_BYTES = 40 * 1024 * 1024
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v"}


def _has_alpha(image):
    return image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)


def compress_photo(uploaded, max_side=1920, quality=82):
    """Photo envoyée -> fichier compressé prêt à enregistrer. Lève forms.ValidationError si elle est refusée.

    Renvoie la valeur telle quelle si ce n'est pas un nouveau fichier (photo déjà enregistrée, case « effacer »).
    """
    if not isinstance(uploaded, UploadedFile):
        return uploaded
    try:
        image = _load_checked(uploaded)
    except AlbumError as error:
        raise forms.ValidationError(str(error))
    base = os.path.splitext(os.path.basename(uploaded.name or "photo"))[0][:60] or "photo"
    image.thumbnail((max_side, max_side), Image.LANCZOS)
    buffer = io.BytesIO()
    if _has_alpha(image):
        image.convert("RGBA").save(buffer, "PNG", optimize=True)
        name = base + ".png"
    else:
        image.convert("RGB").save(buffer, "JPEG", quality=quality, optimize=True, progressive=True)
        name = base + ".jpg"
    return ContentFile(buffer.getvalue(), name=name)


def check_video(uploaded):
    """Vidéo de couverture : 40 Mo au plus, MP4, WebM ou MOV. Lève forms.ValidationError sinon."""
    if not isinstance(uploaded, UploadedFile):
        return uploaded
    extension = os.path.splitext(uploaded.name or "")[1].lower()
    content_type = (getattr(uploaded, "content_type", "") or "").lower()
    if extension not in VIDEO_EXTENSIONS or (content_type and not content_type.startswith("video/")):
        raise forms.ValidationError(_("Vidéo refusée : choisissez un fichier MP4, WebM ou MOV."))
    if uploaded.size > VIDEO_MAX_BYTES:
        raise forms.ValidationError(_("Vidéo trop lourde (40 Mo au plus). Raccourcissez-la ou compressez-la avant de l'envoyer."))
    return uploaded


def _mp4_boxes(handle, start, end):
    """Boîtes (type, début du contenu, fin) d'un fichier MP4/MOV entre `start` et `end`."""
    pos = start
    while pos + 8 <= end:
        handle.seek(pos)
        header = handle.read(8)
        if len(header) < 8:
            return
        size, kind = struct.unpack(">I4s", header)
        body = pos + 8
        if size == 1:
            large = handle.read(8)
            if len(large) < 8:
                return
            size = struct.unpack(">Q", large)[0]
            body = pos + 16
        elif size == 0:
            size = end - pos
        if size < 8:
            return
        yield kind, body, min(pos + size, end)
        pos += size


def video_duration(uploaded):
    """Durée en secondes d'une vidéo MP4 ou MOV (lue dans l'en-tête « mvhd »), ou None si elle est illisible (WebM...)."""
    try:
        handle = uploaded.file if hasattr(uploaded, "file") else uploaded
        handle.seek(0, os.SEEK_END)
        total = handle.tell()
        for kind, body, end in _mp4_boxes(handle, 0, total):
            if kind != b"moov":
                continue
            for sub, sub_body, _sub_end in _mp4_boxes(handle, body, end):
                if sub != b"mvhd":
                    continue
                handle.seek(sub_body)
                version = handle.read(4)[0]
                if version == 1:
                    handle.read(16)
                    scale, length = struct.unpack(">IQ", handle.read(12))
                else:
                    handle.read(8)
                    scale, length = struct.unpack(">II", handle.read(8))
                return length / scale if scale else None
        return None
    except (OSError, struct.error, IndexError, ValueError):
        return None
    finally:
        try:
            handle.seek(0)
        except Exception:  # noqa: BLE001 - le fichier reste utilisable même si on ne peut pas revenir au début
            pass
