"""A StudySpot account, tied to the Auth0 identity that owns it.

Auth0 holds the credentials: the password, its reset, and the proof that an
email address belongs to the person using it. What lives here is only what
StudySpot itself needs to know, which starts with whether someone is a student
or a business owner.

Each account hangs off a Django user whose ``username`` is the Auth0 subject,
as in ``auth0|65f...``. That keeps ``request.user`` an ordinary user, so
permissions and the admin work as they would for any other, while the subject
remains the one identifier Auth0 promises never to change.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

#: What a username a student picks on StudySpot may look like. Auth0 usernames
#: are taken as Auth0 allows them; this applies only to the ones chosen here.
USERNAME_PATTERN = r"^[A-Za-z0-9_.]{3,30}$"
username_validator = RegexValidator(
    USERNAME_PATTERN,
    "Use 3 to 30 letters, numbers, dots or underscores.",
    code="invalid_username",
)


class AccountType(models.TextChoices):
    STUDENT = "student", "Student"
    BUSINESS = "business", "Business"


class Account(models.Model):
    """One person's StudySpot account.

    ``account_type`` is blank between Auth0 sign-up and the step where someone
    says which kind of account they are making. Blank rather than null, so that
    "not chosen yet" has one spelling.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="account"
    )
    account_type = models.CharField(max_length=16, choices=AccountType.choices, blank=True)

    # Copied from the access token on every request, so they follow a change
    # made in Auth0 without anyone having to sync them.
    email = models.EmailField(blank=True)
    email_verified = models.BooleanField(default=False)

    #: From Auth0 when its database connection requires one. Otherwise -- a
    #: connection without usernames, or a log-in with Google -- the student
    #: chooses it when finishing sign-up, and the token never overwrites it.
    username = models.CharField(max_length=150, blank=True)

    business_name = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # "Ada" and "ada" are one person to anyone reading them.
            models.UniqueConstraint(
                Lower("username"),
                condition=~models.Q(username=""),
                name="account_username_unique_ci",
            ),
            # A business account is named; anything else is not.
            models.CheckConstraint(
                condition=(
                    models.Q(account_type=AccountType.BUSINESS) & ~models.Q(business_name="")
                )
                | (~models.Q(account_type=AccountType.BUSINESS) & models.Q(business_name="")),
                name="account_business_name_iff_business",
            ),
        ]

    def __str__(self) -> str:
        return str(self.username or self.email or self.user.username)


class StudentProfile(models.Model):
    """Student discovery details, with an allowlist of publicly shared fields."""

    account = models.OneToOneField(
        Account, on_delete=models.CASCADE, related_name="student_profile"
    )
    school = models.CharField(max_length=160, blank=True)
    courses = models.JSONField(default=list, blank=True)
    topics = models.JSONField(default=list, blank=True)
    study_spot_id = models.TextField(blank=True)
    visible_fields = models.JSONField(default=list, blank=True)
    discoverable = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Student profile for {self.account.username}"


class Favourite(models.Model):
    """One study spot a student has saved.

    Private to the account that made it: nothing exposes another person's
    saves, which is why this is a plain row rather than a field on StudySpot.

    Restored after a merge dropped it. The class had been written on the
    favourites branch and `0002_favourite` creates its table, but the merge of
    develop into that branch resolved this file by taking develop's side, so
    the model vanished while its migration, its views in `favourites.py` and
    its tests all stayed. Keep the fields here in step with that migration.
    """

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="favourites")
    spot = models.ForeignKey("spots.StudySpot", on_delete=models.CASCADE, related_name="favourites")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "spot"], name="favourite_account_spot_unique"
            ),
        ]
        indexes = [
            models.Index(
                fields=["account", "-created_at", "-id"], name="favourite_account_order_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.account_id}: {self.spot_id}"
