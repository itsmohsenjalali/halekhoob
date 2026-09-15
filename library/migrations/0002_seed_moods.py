from django.db import migrations


def seed(apps, schema_editor):
    Mood = apps.get_model("library", "Mood")
    for index, (name, symbol) in enumerate(
        [
            ("امید", "◒"),
            ("شادی", "☼"),
            ("آرامش", "≈"),
            ("انگیزه", "↗"),
            ("اعتمادبه‌نفس", "◇"),
            ("انرژی", "✳"),
        ]
    ):
        Mood.objects.get_or_create(name=name, defaults={"order": index, "symbol": symbol})


class Migration(migrations.Migration):
    dependencies = [("library", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
