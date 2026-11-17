import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Post",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("author_guest_id", models.CharField(blank=True, default="", max_length=64)),
                (
                    "author_kind",
                    models.CharField(
                        choices=[
                            ("guest", "Guest"),
                            ("student", "Student"),
                            ("business", "Business"),
                        ],
                        max_length=16,
                    ),
                ),
                ("author_name", models.CharField(max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("question", "Question"),
                            ("information", "Information"),
                            ("announcement", "Announcement"),
                        ],
                        max_length=16,
                    ),
                ),
                ("title", models.CharField(max_length=160)),
                ("body", models.TextField(max_length=10000)),
                (
                    "author_account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="accounts.account",
                    ),
                ),
            ],
            options={
                "ordering": ["-id"],
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="Tag",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("subject", "Subject"),
                            ("university", "University"),
                            ("spot", "Study spot"),
                        ],
                        max_length=16,
                    ),
                ),
                ("key", models.CharField(max_length=360)),
                ("label", models.TextField()),
            ],
            options={
                "ordering": ["kind", "key"],
                "constraints": [
                    models.UniqueConstraint(fields=("kind", "key"), name="board_tag_identity"),
                    models.CheckConstraint(
                        condition=models.Q(("kind__in", ["subject", "university", "spot"])),
                        name="board_tag_kind",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PostTag",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "post",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tag_links",
                        to="board.post",
                    ),
                ),
                (
                    "tag",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="post_links",
                        to="board.tag",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="post",
            name="tags",
            field=models.ManyToManyField(
                related_name="posts", through="board.PostTag", to="board.tag"
            ),
        ),
        migrations.CreateModel(
            name="Comment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("author_guest_id", models.CharField(blank=True, default="", max_length=64)),
                (
                    "author_kind",
                    models.CharField(
                        choices=[
                            ("guest", "Guest"),
                            ("student", "Student"),
                            ("business", "Business"),
                        ],
                        max_length=16,
                    ),
                ),
                ("author_name", models.CharField(max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("body", models.TextField(max_length=3000)),
                (
                    "author_account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="accounts.account",
                    ),
                ),
                (
                    "post",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comments",
                        to="board.post",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
                "abstract": False,
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("author_account__isnull", True),
                                ("author_kind", "guest"),
                                models.Q(("author_guest_id", ""), _negated=True),
                            ),
                            models.Q(
                                ("author_guest_id", ""),
                                ("author_kind__in", ["student", "business"]),
                            ),
                            _connector="OR",
                        ),
                        name="board_comment_author_stamp",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Report",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "target_kind",
                    models.CharField(
                        choices=[("post", "Post"), ("comment", "Comment")], max_length=16
                    ),
                ),
                ("target_id", models.PositiveBigIntegerField()),
                ("target_title", models.CharField(blank=True, max_length=160)),
                ("target_body", models.TextField()),
                (
                    "target_author_kind",
                    models.CharField(
                        choices=[
                            ("guest", "Guest"),
                            ("student", "Student"),
                            ("business", "Business"),
                        ],
                        max_length=16,
                    ),
                ),
                ("target_author_name", models.CharField(max_length=200)),
                ("reporter_guest_id", models.CharField(blank=True, default="", max_length=64)),
                (
                    "reporter_kind",
                    models.CharField(
                        choices=[
                            ("guest", "Guest"),
                            ("student", "Student"),
                            ("business", "Business"),
                        ],
                        max_length=16,
                    ),
                ),
                ("reporter_name", models.CharField(max_length=200)),
                ("reason", models.TextField(max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "reporter_account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="accounts.account",
                    ),
                ),
            ],
            options={
                "ordering": ["-id"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("reporter_account__isnull", True),
                                ("reporter_kind", "guest"),
                                models.Q(("reporter_guest_id", ""), _negated=True),
                            ),
                            models.Q(
                                ("reporter_guest_id", ""),
                                ("reporter_kind__in", ["student", "business"]),
                            ),
                            _connector="OR",
                        ),
                        name="board_report_stamp",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("target_kind__in", ["post", "comment"])),
                        name="board_report_target_kind",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("reporter_account__isnull", False)),
                        fields=("target_kind", "target_id", "reporter_account"),
                        name="board_report_account_unique",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("reporter_kind", "guest")),
                        fields=("target_kind", "target_id", "reporter_guest_id"),
                        name="board_report_guest_unique",
                    ),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="posttag",
            constraint=models.UniqueConstraint(
                fields=("post", "tag"), name="board_post_tag_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="post",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("author_account__isnull", True),
                        ("author_kind", "guest"),
                        models.Q(("author_guest_id", ""), _negated=True),
                    ),
                    models.Q(("author_guest_id", ""), ("author_kind__in", ["student", "business"])),
                    _connector="OR",
                ),
                name="board_post_author_stamp",
            ),
        ),
        migrations.AddConstraint(
            model_name="post",
            constraint=models.CheckConstraint(
                condition=models.Q(("kind__in", ["question", "information", "announcement"])),
                name="board_post_kind",
            ),
        ),
    ]
