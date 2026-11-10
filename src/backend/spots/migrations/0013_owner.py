"""Let a business account own the spots it lists.

Nullable, because every spot already in the table came from a city dataset and
has no owner on StudySpot. A plain AddField: ``owner`` is not part of
``search_vector``, so the generated column is untouched. Django indexes the
foreign key itself, which is what ``GET /listings`` filters on.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("spots", "0012_osm_attributes"),
    ]

    operations = [
        migrations.AddField(
            model_name="studyspot",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                help_text="The business account that manages this listing; null for imported spots.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="listings",
                to="accounts.account",
            ),
        ),
    ]
