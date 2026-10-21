import secrets

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def fill_entry_codes(apps, schema_editor):
    """Les invités déjà créés reçoivent leur code d'entrée."""
    Guest = apps.get_model("events", "Guest")
    used = set()
    for guest in Guest.objects.filter(entry_code__isnull=True):
        while True:
            code = "EL-" + "".join(secrets.choice(ALPHABET) for _ in range(4)) + "-" + "".join(secrets.choice(ALPHABET) for _ in range(4))
            if code not in used:
                used.add(code)
                break
        guest.entry_code = code
        guest.save(update_fields=["entry_code"])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("events", "0003_guest_language"),
    ]

    operations = [
        migrations.AddField(
            model_name="guest",
            name="added_on_site",
            field=models.BooleanField(default=False, verbose_name="ajouté sur place"),
        ),
        migrations.AddField(
            model_name="guest",
            name="checked_in_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="arrivé le"),
        ),
        migrations.AddField(
            model_name="guest",
            name="entry_code",
            field=models.CharField(editable=False, max_length=14, null=True, verbose_name="code d'entrée"),
        ),
        migrations.RunPython(fill_entry_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="guest",
            name="entry_code",
            field=models.CharField(editable=False, max_length=14, unique=True, verbose_name="code d'entrée"),
        ),
        migrations.CreateModel(
            name="CheckIn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(blank=True, max_length=60, verbose_name="code lu")),
                ("result", models.CharField(choices=[("validated", "Entrée validée"), ("duplicate", "QR déjà utilisé"), ("unknown", "QR inconnu"), ("wrong_event", "Autre événement"), ("walk_in", "Ajouté sur place"), ("cancelled", "Pointage annulé")], max_length=12, verbose_name="résultat")),
                ("source", models.CharField(choices=[("qr", "QR code"), ("manual", "Recherche"), ("walk_in", "Sur place")], default="qr", max_length=10, verbose_name="origine")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="check_ins", to="events.event", verbose_name="événement")),
                ("guest", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="check_ins", to="events.guest", verbose_name="invité")),
                ("scanned_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "pointage",
                "verbose_name_plural": "pointages",
                "ordering": ["-created_at", "-pk"],
            },
        ),
    ]
