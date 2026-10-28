"""HTTP input and public output for communities."""

from rest_framework import serializers

from .models import Channel, Community, Membership


class CommunityWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, trim_whitespace=True)
    description = serializers.CharField(max_length=1000, allow_blank=True, required=False)
    school = serializers.CharField(max_length=100, allow_blank=True, required=False)
    course = serializers.CharField(max_length=100, allow_blank=True, required=False)


class CommunitySerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)
    role = serializers.CharField(read_only=True)

    class Meta:
        model = Community
        fields = [
            "id",
            "name",
            "description",
            "school",
            "course",
            "owner_id",
            "created_at",
            "member_count",
            "role",
        ]


class ChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Channel
        fields = ["id", "name", "position", "archived"]


class ChannelWriteSerializer(serializers.Serializer):
    name = serializers.RegexField(r"^[a-z0-9][a-z0-9-]{0,49}$")


class MemberSerializer(serializers.ModelSerializer):
    user_id = serializers.CharField(read_only=True)
    display_name = serializers.SerializerMethodField()
    is_me = serializers.SerializerMethodField()

    def get_display_name(self, member: Membership) -> str:
        account = getattr(member.user, "account", None)
        return account.username if account and account.username else member.user.get_username()

    def get_is_me(self, member: Membership) -> bool:
        request = self.context["request"]
        return bool(
            getattr(request.user, "is_authenticated", False) and request.user.pk == member.user_id
        )

    class Meta:
        model = Membership
        fields = ["user_id", "display_name", "is_me", "role", "joined_at"]


class InviteWriteSerializer(serializers.Serializer):
    expires_in_hours = serializers.IntegerField(min_value=1, max_value=720, required=False)
    max_uses = serializers.IntegerField(min_value=1, max_value=1000, required=False)


class RoleWriteSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Membership.Role.choices)
