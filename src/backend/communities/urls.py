from django.urls import path

from . import dm_views, message_views, views

urlpatterns = [
    path("dms", dm_views.DirectConversations.as_view()),
    path("dms/<int:conversation_id>/messages", dm_views.DirectMessages.as_view()),
    path(
        "dms/<int:conversation_id>/messages/<int:message_id>",
        dm_views.DirectMessageDetail.as_view(),
    ),
    path("communities", views.CommunityList.as_view()),
    path("communities/<int:community_id>", views.CommunityDetail.as_view()),
    path("communities/<int:community_id>/join", views.Join.as_view()),
    path("communities/<int:community_id>/leave", views.Leave.as_view()),
    path("communities/<int:community_id>/members", views.Members.as_view()),
    path("communities/<int:community_id>/members/<str:user_id>", views.MemberDetail.as_view()),
    path("communities/<int:community_id>/transfer", views.Transfer.as_view()),
    path("communities/<int:community_id>/channels", views.Channels.as_view()),
    path("communities/<int:community_id>/channels/<int:channel_id>", views.ChannelDetail.as_view()),
    path("communities/<int:community_id>/messages/search", message_views.MessageSearch.as_view()),
    path(
        "communities/<int:community_id>/channels/<int:channel_id>/messages",
        message_views.Messages.as_view(),
    ),
    path(
        "communities/<int:community_id>/channels/<int:channel_id>/pins",
        message_views.Pins.as_view(),
    ),
    path(
        "communities/<int:community_id>/channels/<int:channel_id>/messages/<int:message_id>",
        message_views.MessageDetail.as_view(),
    ),
    path(
        "communities/<int:community_id>/channels/<int:channel_id>/messages/<int:message_id>/pin",
        message_views.MessagePin.as_view(),
    ),
    path(
        "communities/<int:community_id>/channels/<int:channel_id>/messages/<int:message_id>/dm",
        dm_views.StartFromMessage.as_view(),
    ),
    path(
        "communities/<int:community_id>/channels/<int:channel_id>/messages/<int:message_id>/reactions",
        message_views.MessageReactions.as_view(),
    ),
    path(
        "communities/<int:community_id>/channels/<int:channel_id>/messages/<int:message_id>/reactions/<str:emoji>",
        message_views.MessageReactions.as_view(),
    ),
    path("communities/<int:community_id>/invites", views.Invites.as_view()),
    path("communities/<int:community_id>/invites/<int:invite_id>", views.InviteDetail.as_view()),
    path("communities/invites/<str:token>/redeem", views.Redeem.as_view()),
    path("communities/<int:community_id>/moderation", views.Moderation.as_view()),
    path("communities/<int:community_id>/dms", dm_views.StartFromMember.as_view()),
    path("communities/<int:community_id>/admin", views.AdminCommunity.as_view()),
]
