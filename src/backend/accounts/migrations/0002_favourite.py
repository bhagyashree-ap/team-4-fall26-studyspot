import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("spots", "0012_osm_attributes"),
    ]

    operations = [
        migrations.CreateModel(
            name="Favourite",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favourites",
                        to="accounts.account",
                    ),
                ),
                (
                    "spot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favourites",
                        to="spots.studyspot",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("account", "spot"), name="favourite_account_spot_unique"
                    ),
                ],
                "indexes": [
                    models.Index(
                        fields=["account", "-created_at", "-id"],
                        name="favourite_account_order_idx",
                    ),
                ],
            },
        ),
    ]
