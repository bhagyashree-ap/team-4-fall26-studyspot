"""Session-specific sample conversations for the opt-in local chat demo."""

import hashlib
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .guest_names import guest_name
from .models import (
    Community,
    ConversationParticipant,
    DirectConversation,
    DirectMessage,
    DirectReaction,
    Poll,
    Vote,
)
from .views import CommunitySessionAuthentication, ensure_guest_id, guest_expiry


def ensure_demo_group(identity: str, key: str) -> None:
    group_key = hashlib.sha256(f"{key}\0demo-study-group".encode()).hexdigest()
    group, created = DirectConversation.objects.get_or_create(
        pair_key=group_key,
        defaults={
            "kind": DirectConversation.Kind.GROUP,
            "name": "Thursday study crew",
            "first_key": "",
            "second_key": "",
            "first_name": "",
            "second_name": "",
        },
    )
    if not created:
        return
    participants = [
        (key, guest_name(identity)),
        (f"g:{identity}:maya", "Maya Chen"),
        (f"g:{identity}:jordan", "Jordan Rivera"),
    ]
    ConversationParticipant.objects.bulk_create(
        [
            ConversationParticipant(conversation=group, actor=actor, name=name)
            for actor, name in participants
        ]
    )
    first = DirectMessage.objects.create(
        conversation=group,
        sender_key=f"g:{identity}:maya",
        author_name="Maya Chen",
        content="Thursday at Bobst? I can bring the chapter 4 practice problems. 📚",
    )
    DirectMessage.objects.create(
        conversation=group,
        sender_key=f"g:{identity}:jordan",
        author_name="Jordan Rivera",
        content="That works for me. Let's meet on the fourth floor at 6.",
        reply_to=first,
    )
    DirectMessage.objects.create(
        conversation=group,
        sender_key=key,
        author_name=guest_name(identity),
        content="Perfect — I'll bring my notes from office hours.",
    )


class MessageDemo(APIView):
    authentication_classes = [CommunitySessionAuthentication]

    def check_permissions(self, request: Request) -> None:
        if not settings.DEBUG or not settings.CHAT_GUEST_DEMO:
            raise NotFound()
        super().check_permissions(request)

    @transaction.atomic
    def post(self, request: Request) -> Response:
        identity = ensure_guest_id(request)
        key = f"g:{identity}"
        community_id = request.session.get("messages_demo_community")
        if community_id and Community.objects.filter(pk=community_id).exists():
            ensure_demo_group(identity, key)
            return Response({"ready": True})

        community = services.create_guest_community(
            {
                "name": "StudySpot demo lounge",
                "description": "A local space to explore messages, polls, threads, and study plans.",
                "school": "New York University",
                "course": "Study together",
            },
            identity,
            guest_expiry(request),
        )
        request.session["guest_communities"] = [
            *request.session.get("guest_communities", []),
            community.pk,
        ]
        call_command("seed_sample_communities", guest_community=community.pk, stdout=StringIO())
        conversations = DirectConversation.objects.filter(Q(first_key=key) | Q(second_key=key))
        for conversation in conversations:
            other = (
                conversation.second_key if conversation.first_key == key else conversation.first_key
            )
            name = (
                conversation.second_name
                if conversation.first_key == key
                else conversation.first_name
            )
            # Only enrich the two sample participants created by the command.
            if name not in {"Maya Chen", "Jordan Rivera"}:
                continue
            root = DirectMessage.objects.create(
                conversation=conversation,
                sender_key=other,
                author_name=name,
                content="Let's meet at **Bobst Library** this week. Bring your questions and a coffee ☕",
                pinned_at=timezone.now(),
            )
            DirectReaction.objects.create(message=root, actor=key, emoji="☕")
            DirectReaction.objects.create(message=root, actor=other, emoji="👍")
            DirectMessage.objects.create(
                conversation=conversation,
                sender_key=key,
                author_name=guest_name(identity),
                content="Sounds good! I can bring the practice problems. Which day works best?",
                reply_to=root,
            )
            DirectMessage.objects.create(
                conversation=conversation,
                sender_key=other,
                author_name=name,
                content="I reserved the table near the windows. We can use this thread to plan.",
                thread_root=root,
            )
            poll = Poll.objects.create(
                options=["Wednesday at 4 pm", "Thursday at 6 pm", "Saturday at 11 am"]
            )
            DirectMessage.objects.create(
                conversation=conversation,
                sender_key=other,
                author_name=name,
                content="When should we study together?",
                poll=poll,
            )
            Vote.objects.create(poll=poll, actor=other, choice=1)
            DirectMessage.objects.create(
                conversation=conversation,
                sender_key=other,
                author_name=name,
                content="Here's a small checklist for our session. You can download it below.",
                file_name="study-checklist.txt",
                file_bytes=b"Study session checklist\n- Review notes\n- Bring practice problems\n- Take a break\n",
            )
            DirectMessage.objects.create(
                conversation=conversation,
                sender_key=key,
                author_name=guest_name(identity),
                content="My plan: review notes, try the questions, then compare solutions.\n\n```python\nfor question in practice_set:\n    try_it_first(question)\n```",
            )
        ensure_demo_group(identity, key)
        request.session["messages_demo_community"] = community.pk
        return Response({"ready": True})
