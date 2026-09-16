import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    # Separate transaction: PostgreSQL must commit legacy data's deferred FK triggers first.
    dependencies = [('library', '0005_account_dailyusage_cloudobject_owner_mood_owner_and_more')]
    operations = [migrations.AlterField(
        model_name='mood', name='owner',
        field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='moods', to=settings.AUTH_USER_MODEL),
    )]
