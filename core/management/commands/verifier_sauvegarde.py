"""Vérifie qu'une sauvegarde se restaure vraiment (point 20 de docs/solidite.md).

    python manage.py verifier_sauvegarde                       # la plus récente du dossier backups/
    python manage.py verifier_sauvegarde backups/eventlead-20261004-120000.zip

La sauvegarde est restaurée dans une base temporaire, à côté (la base du site n'est jamais touchée) :
création des tables, chargement de toutes les données, puis comparaison du nombre de lignes de chaque table
avec ce qui a été sauvegardé, et contrôle de chaque photo du fichier. La base temporaire est ensuite effacée.
"""
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.utils import load_backend

from .sauvegarder import backup_dir, model_counts

ALIAS = "verification_sauvegarde"


class Command(BaseCommand):
    help = "Restaure une sauvegarde dans une base temporaire et vérifie qu'il ne manque rien."

    def add_arguments(self, parser):
        parser.add_argument("fichier", nargs="?", default="", help="Fichier .zip (défaut : la sauvegarde la plus récente).")

    def handle(self, *args, **options):
        path = Path(options["fichier"]) if options["fichier"] else None
        if path is None:
            found = sorted(backup_dir().glob("eventlead-*.zip"))
            if not found:
                raise CommandError("Aucune sauvegarde trouvée. Lancez d'abord : python manage.py sauvegarder")
            path = found[-1]
        if not path.is_file():
            raise CommandError(f"Fichier introuvable : {path}")
        self.stdout.write(f"Vérification de {path} ...")

        problems = []
        with zipfile.ZipFile(path) as archive:
            broken = archive.testzip()
            if broken:
                raise CommandError(f"Fichier abîmé dans la sauvegarde : {broken}")
            names = set(archive.namelist())
            if not {"data.json", "manifest.json"} <= names:
                raise CommandError("Ce fichier n'est pas une sauvegarde EventLead (data.json ou manifest.json manquant).")
            manifest = json.loads(archive.read("manifest.json"))
            for name, size in manifest.get("media", {}).items():
                member = "media/" + name
                if member not in names:
                    problems.append(f"photo manquante : {name}")
                elif archive.getinfo(member).file_size != size:
                    problems.append(f"photo de taille différente : {name}")
            workdir = Path(tempfile.mkdtemp(prefix="eventlead-verif-"))
            try:
                data_file = workdir / "data.json"
                data_file.write_bytes(archive.read("data.json"))
                restored = self._restore(workdir, data_file)
            finally:
                temporary = getattr(connections._connections, ALIAS, None)
                if temporary is not None:
                    temporary.close()
                    del connections[ALIAS]
                shutil.rmtree(workdir, ignore_errors=True)

        for label, expected in sorted(manifest["counts"].items()):
            got = restored.get(label)
            if got != expected:
                problems.append(f"{label} : {expected} ligne(s) sauvegardée(s), {got} restaurée(s)")
        total = sum(manifest["counts"].values())
        if problems:
            for problem in problems:
                self.stdout.write(self.style.ERROR(" - " + problem))
            raise CommandError(f"La sauvegarde NE se restaure PAS correctement ({len(problems)} problème(s)).")
        self.stdout.write(self.style.SUCCESS(
            f"Sauvegarde valide : {total} lignes dans {len(manifest['counts'])} tables et "
            f"{len(manifest.get('media', {}))} fichiers médias restaurés sans écart (sauvegarde du {manifest['created_at'][:16]})."
        ))
        self.stdout.write(
            "Pour restaurer pour de vrai sur une base vide : python manage.py migrate, "
            "puis python manage.py loaddata data.json (extrait du .zip), puis copier le dossier media/ du .zip."
        )

    def _restore(self, workdir, data_file):
        """Crée une base SQLite temporaire, y charge les données et renvoie le nombre de lignes par table."""
        config = connections.configure_settings({
            "default": connections.settings["default"],
            ALIAS: {"ENGINE": "django.db.backends.sqlite3", "NAME": str(workdir / "verif.sqlite3")},
        })[ALIAS]
        # Connexion ajoutée pour la durée de la vérification seulement (jamais dans les réglages du site)
        connections[ALIAS] = load_backend(config["ENGINE"]).DatabaseWrapper(config, ALIAS)
        call_command("migrate", database=ALIAS, verbosity=0, interactive=False)
        try:
            call_command("loaddata", str(data_file), database=ALIAS, verbosity=0)
        except Exception as error:
            raise CommandError(f"Les données ne se rechargent pas : {error}")
        return model_counts(using=ALIAS)
