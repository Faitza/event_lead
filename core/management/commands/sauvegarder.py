"""Sauvegarde complète du site dans un seul fichier .zip (point 20 de docs/solidite.md).

    python manage.py sauvegarder                 # backups/eventlead-AAAAMMJJ-HHMMSS.zip
    python manage.py sauvegarder --garder 14     # ne garde que les 14 plus récentes (défaut)
    python manage.py sauvegarder --sans-medias   # seulement la base (plus léger)

Le fichier contient : data.json (toutes les données, lisibles par n'importe quelle base),
manifest.json (nombre de lignes par table, liste des photos) et le dossier media/ (photos, vidéos).
Vérifier ensuite qu'il se restaure : python manage.py verifier_sauvegarde
"""
import io
import json
import zipfile
from pathlib import Path

import django
from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

EXCLUDED = ["contenttypes", "auth.permission", "sessions", "admin.logentry"]


def backup_dir():
    return Path(getattr(settings, "BACKUP_DIR", settings.BASE_DIR / "backups"))


def model_counts(using="default"):
    """Nombre de lignes de chaque table sauvegardée."""
    counts = {}
    for model in apps.get_models():
        label = model._meta.label_lower
        if model._meta.proxy or not model._meta.managed or label.split(".")[0] in EXCLUDED or label in EXCLUDED:
            continue
        counts[label] = model._default_manager.using(using).count()
    return counts


class Command(BaseCommand):
    help = "Sauvegarde la base de données et les photos dans un fichier .zip."

    def add_arguments(self, parser):
        parser.add_argument("--garder", type=int, default=14, help="Nombre de sauvegardes gardées (les plus anciennes sont effacées).")
        parser.add_argument("--sans-medias", action="store_true", help="Ne pas inclure les photos et vidéos.")
        parser.add_argument("--dossier", default="", help="Dossier de destination (défaut : backups/).")

    def handle(self, *args, **options):
        target_dir = Path(options["dossier"]) if options["dossier"] else backup_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        target = target_dir / f"eventlead-{stamp}.zip"
        partial = target.with_suffix(".zip.part")

        data = io.StringIO()
        call_command("dumpdata", natural_foreign=True, natural_primary=True, exclude=EXCLUDED, stdout=data)
        media_root = Path(settings.MEDIA_ROOT)
        media = []
        if not options["sans_medias"] and media_root.is_dir():
            media = sorted(p for p in media_root.rglob("*") if p.is_file())
        manifest = {
            "created_at": timezone.now().isoformat(), "django": django.get_version(),
            "counts": model_counts(), "media": {p.relative_to(media_root).as_posix(): p.stat().st_size for p in media},
        }
        # Écrit d'abord un fichier .part : une sauvegarde interrompue ne passe jamais pour une sauvegarde complète
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("data.json", data.getvalue())
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            for path in media:
                archive.write(path, "media/" + path.relative_to(media_root).as_posix())
        partial.replace(target)

        removed = 0
        for old in sorted(target_dir.glob("eventlead-*.zip"))[:-max(options["garder"], 1)]:
            old.unlink()
            removed += 1
        rows = sum(manifest["counts"].values())
        size = target.stat().st_size / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(
            f"Sauvegarde créée : {target} ({size:.1f} Mo, {rows} lignes, {len(media)} fichiers médias)."
        ))
        if removed:
            self.stdout.write(f"{removed} ancienne(s) sauvegarde(s) effacée(s).")
        self.stdout.write("Vérifiez qu'elle se restaure : python manage.py verifier_sauvegarde")
