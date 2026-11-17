from django.conf import settings
from django.db import models


class AuthorKind(models.TextChoices):
    GUEST = "guest", "Guest"
    STUDENT = "student", "Student"
    BUSINESS = "business", "Business"


def ownership_constraint(prefix: str) -> models.Q:
    return (
        models.Q(**{f"{prefix}_kind": AuthorKind.GUEST, f"{prefix}_account__isnull": True})
        & ~models.Q(**{f"{prefix}_guest_id": ""})
    ) | models.Q(
        **{
            f"{prefix}_kind__in": [AuthorKind.STUDENT, AuthorKind.BUSINESS],
            f"{prefix}_guest_id": "",
        }
    )


class Authored(models.Model):
    author_account = models.ForeignKey(
        "accounts.Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    author_guest_id = models.CharField(max_length=64, blank=True, default="")
    author_kind = models.CharField(max_length=16, choices=AuthorKind.choices)
    author_name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        constraints = [
            models.CheckConstraint(
                condition=ownership_constraint("author"),
                name="%(app_label)s_%(class)s_author_stamp",
            )
        ]


class PostKind(models.TextChoices):
    QUESTION = "question", "Question"
    INFORMATION = "information", "Information"
    ANNOUNCEMENT = "announcement", "Announcement"


class Post(Authored):
    kind = models.CharField(max_length=16, choices=PostKind.choices)
    title = models.CharField(max_length=160)
    body = models.TextField(max_length=10000)
    tags = models.ManyToManyField("Tag", through="PostTag", related_name="posts")

    class Meta(Authored.Meta):
        ordering = ["-id"]
        constraints = [
            *Authored.Meta.constraints,
            models.CheckConstraint(
                condition=models.Q(kind__in=PostKind.values), name="board_post_kind"
            ),
        ]

    def __str__(self) -> str:
        return str(self.title)


class Comment(Authored):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    body = models.TextField(max_length=3000)

    class Meta(Authored.Meta):
        ordering = ["id"]

    def __str__(self) -> str:
        return str(self.body)[:80]


class TagKind(models.TextChoices):
    SUBJECT = "subject", "Subject"
    UNIVERSITY = "university", "University"
    SPOT = "spot", "Study spot"


class Tag(models.Model):
    kind = models.CharField(max_length=16, choices=TagKind.choices)
    key = models.CharField(max_length=360)
    label = models.TextField()

    class Meta:
        ordering = ["kind", "key"]
        constraints = [
            models.UniqueConstraint(fields=["kind", "key"], name="board_tag_identity"),
            models.CheckConstraint(
                condition=models.Q(kind__in=TagKind.values), name="board_tag_kind"
            ),
        ]

    def __str__(self) -> str:
        return str(self.label)


class PostTag(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="tag_links")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="post_links")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["post", "tag"], name="board_post_tag_unique")
        ]

    def __str__(self) -> str:
        return f"{self.post_id}/{self.tag_id}"


class Report(models.Model):
    class TargetKind(models.TextChoices):
        POST = "post", "Post"
        COMMENT = "comment", "Comment"

    target_kind = models.CharField(max_length=16, choices=TargetKind.choices)
    target_id = models.PositiveBigIntegerField()
    target_title = models.CharField(max_length=160, blank=True)
    target_body = models.TextField()
    target_author_kind = models.CharField(max_length=16, choices=AuthorKind.choices)
    target_author_name = models.CharField(max_length=200)
    reporter_account = models.ForeignKey(
        "accounts.Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reporter_guest_id = models.CharField(max_length=64, blank=True, default="")
    reporter_kind = models.CharField(max_length=16, choices=AuthorKind.choices)
    reporter_name = models.CharField(max_length=200)
    reason = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(
                condition=ownership_constraint("reporter"), name="board_report_stamp"
            ),
            models.CheckConstraint(
                condition=models.Q(target_kind__in=["post", "comment"]),
                name="board_report_target_kind",
            ),
            models.UniqueConstraint(
                fields=["target_kind", "target_id", "reporter_account"],
                condition=models.Q(reporter_account__isnull=False),
                name="board_report_account_unique",
            ),
            models.UniqueConstraint(
                fields=["target_kind", "target_id", "reporter_guest_id"],
                condition=models.Q(reporter_kind=AuthorKind.GUEST),
                name="board_report_guest_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.target_kind} {self.target_id}"
