import django.db.models.deletion
from django.db import migrations, models


def ensure_profiles(apps, schema_editor):
    Account = apps.get_model("accounts", "Account")
    StudentProfile = apps.get_model("accounts", "StudentProfile")
    StudentProfile.objects.bulk_create(
        [
            StudentProfile(account_id=pk)
            for pk in Account.objects.filter(account_type="student").values_list("pk", flat=True)
        ],
        ignore_conflicts=True,
        batch_size=500,
    )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="StudentProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("school", models.CharField(blank=True, max_length=160)),
                ("courses", models.JSONField(blank=True, default=list)),
                ("topics", models.JSONField(blank=True, default=list)),
                ("study_spot_id", models.TextField(blank=True)),
                ("visible_fields", models.JSONField(blank=True, default=list)),
                ("discoverable", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "account",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="student_profile",
                        to="accounts.account",
                    ),
                ),
            ],
        ),
        migrations.RunPython(ensure_profiles, migrations.RunPython.noop),
    ]
