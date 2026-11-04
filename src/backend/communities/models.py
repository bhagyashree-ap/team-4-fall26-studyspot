"""Public communities and their membership boundaries."""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.db import models
from django.db.models.functions import Lower


class Community(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(max_length=1000, blank=True)
    school = models.CharField(max_length=100, blank=True)
    course = models.CharField(max_length=100, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.name}"


class Membership(models.Model):
    class Role(models.TextChoices):
        MEMBER = "member"
        MODERATOR = "moderator"

    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["community", "user"], name="member_once")]
        indexes = [models.Index(fields=["user", "community"], name="member_user_community")]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.community_id}"


class GuestMembership(models.Model):
    community = models.ForeignKey(
        Community, on_delete=models.CASCADE, related_name="guest_memberships"
    )
    guest_id = models.CharField(max_length=32)
    joined_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["community", "guest_id"], name="guest_member_once")
        ]
        indexes = [models.Index(fields=["expires_at"], name="guest_membership_expiry")]

    def __str__(self) -> str:
        return f"Guest in {self.community_id}"


class Channel(models.Model):
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="channels")
    name = models.CharField(max_length=50)
    position = models.PositiveSmallIntegerField(default=0)
    private = models.BooleanField(default=False)
    read_only = models.BooleanField(default=False)
    slowmode_seconds = models.PositiveIntegerField(default=0)
    topic = models.CharField(max_length=256, blank=True)
    archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(Lower("name"), "community", name="channel_name_per_community")
        ]

    def __str__(self) -> str:
        return f"{self.name}"


class Poll(models.Model):
    options = models.JSONField()

    def __str__(self) -> str:
        return f"poll {self.pk}"


class Vote(models.Model):
    poll = models.ForeignKey(Poll, related_name="votes", on_delete=models.CASCADE)
    actor = models.CharField(max_length=128)
    choice = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["poll", "actor"], name="vote_once")]

    def __str__(self) -> str:
        return f"vote on poll {self.poll_id}"


class ChatMessageQuery(models.Manager):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .defer("file_bytes")
            .select_related("poll")
            .prefetch_related("poll__votes")
        )


class ChatMessage(models.Model):
    mentions = ArrayField(models.CharField(max_length=180), default=list, blank=True)
    poll = models.OneToOneField(
        Poll, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    thread_root = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="thread_messages"
    )
    file_name = models.CharField(max_length=255, blank=True)
    file_bytes = models.BinaryField(null=True)
    objects = ChatMessageQuery()

    class Meta:
        abstract = True


class Message(ChatMessage):
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    guest_id = models.CharField(max_length=32, blank=True)
    author_name = models.CharField(max_length=150)
    content = models.TextField(max_length=2000)
    reply_to = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    pinned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["channel", "id"], name="message_channel_id"),
            GinIndex(SearchVector("content", config="english"), name="message_content_fts"),
        ]

    def __str__(self) -> str:
        return f"Message {self.pk} in {self.channel_id}"


class Reaction(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="reactions")
    emoji = models.CharField(max_length=32)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True
    )
    guest_id = models.CharField(max_length=32, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "emoji", "user"],
                condition=models.Q(user__isnull=False),
                name="reaction_once_per_user",
            ),
            models.UniqueConstraint(
                fields=["message", "emoji", "guest_id"],
                condition=~models.Q(guest_id=""),
                name="reaction_once_per_guest",
            ),
            models.CheckConstraint(
                condition=(models.Q(user__isnull=False) & models.Q(guest_id=""))
                | (models.Q(user__isnull=True) & ~models.Q(guest_id="")),
                name="reaction_one_actor",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.emoji} on {self.message_id}"


class DirectConversation(models.Model):
    pair_key = models.CharField(max_length=64, unique=True)
    first_key = models.CharField(max_length=128)
    second_key = models.CharField(max_length=128)
    first_name = models.CharField(max_length=150)
    second_name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["first_key", "-updated_at"], name="dm_first_recent"),
            models.Index(fields=["second_key", "-updated_at"], name="dm_second_recent"),
        ]

    def __str__(self) -> str:
        return f"Direct conversation {self.pk}"


class DirectMessage(ChatMessage):
    pinned_at = models.DateTimeField(null=True, blank=True)
    conversation = models.ForeignKey(
        DirectConversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender_key = models.CharField(max_length=128)
    author_name = models.CharField(max_length=150)
    content = models.TextField(max_length=2000)
    reply_to = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["conversation", "id"], name="dm_message_page")]

    def __str__(self) -> str:
        return f"Direct message {self.pk}"


class DirectReaction(models.Model):
    message = models.ForeignKey(DirectMessage, related_name="reactions", on_delete=models.CASCADE)
    actor = models.CharField(max_length=128)
    emoji = models.CharField(max_length=32)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "actor", "emoji"], name="direct_reaction_once"
            )
        ]

    def __str__(self) -> str:
        return f"{self.emoji} on direct message {self.message_id}"


class Ban(models.Model):
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="bans")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["community", "user"], name="ban_once")]

    def __str__(self) -> str:
        return f"{self.user_id} banned from {self.community_id}"


class Invite(models.Model):
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="invites")
    token_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    uses = models.PositiveIntegerField(default=0)
    revoked = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"Invite {self.pk} for {self.community_id}"


class ModerationEvent(models.Model):
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="moderation")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    target = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    action = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.action} in {self.community_id}"


class RoomMemberState(models.Model):
    channel = models.ForeignKey(Channel, null=True, on_delete=models.CASCADE)
    conversation = models.ForeignKey(DirectConversation, null=True, on_delete=models.CASCADE)
    actor = models.CharField(max_length=128)
    name = models.CharField(max_length=150)
    last_active = models.DateTimeField(auto_now=True)

    class Alerts(models.TextChoices):
        ALL = "all"
        MENTIONS = "mentions"
        MUTED = "muted"

    alerts = models.CharField(max_length=8, choices=Alerts.choices, default=Alerts.ALL)
    last_read = models.PositiveBigIntegerField(default=0)
    typing_until = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(channel__isnull=True, conversation__isnull=False)
                    | models.Q(channel__isnull=False, conversation__isnull=True)
                ),
                name="one_chat_room",
            ),
            models.UniqueConstraint(fields=["channel", "actor"], name="channel_actor_state"),
            models.UniqueConstraint(fields=["conversation", "actor"], name="dm_actor_state"),
        ]

    def __str__(self) -> str:
        return f"room preferences {self.pk}"
