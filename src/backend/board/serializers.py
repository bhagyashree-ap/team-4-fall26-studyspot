import unicodedata
from collections.abc import Mapping

from rest_framework import serializers

from spots.models import StudySpot

from .identity import owns
from .models import Comment, Post, PostKind, Tag, TagKind

TAG_LIMITS = {TagKind.SUBJECT: 80, TagKind.UNIVERSITY: 120, TagKind.SPOT: 255}
MAX_ID = 2**63 - 1
FILLER_AND_BLANK_CHARACTERS = frozenset("\u115f\u1160\u2800\u3164\uffa0")


def normalize_text(value: str) -> tuple[str, str]:
    label = " ".join(unicodedata.normalize("NFKC", value).split())
    return label.casefold(), label


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = data.keys() - self.fields.keys()
            if unknown:
                raise serializers.ValidationError(
                    {key: "This field is not writable." for key in sorted(unknown)}
                )
        return super().to_internal_value(data)


class TextField(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        value = super().to_internal_value(data)
        # Marks and format controls need a visible base; Unicode fillers are blank letters.
        if not any(
            unicodedata.category(char)[0] in "LNPS" and char not in FILLER_AND_BLANK_CHARACTERS
            for char in value
        ):
            self.fail("blank")
        return value


class TagInputSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=TagKind.choices)
    value = TextField()

    def validate(self, attrs):
        # A partial post edit still requires complete replacement tag values.
        if "kind" not in attrs or "value" not in attrs:
            raise serializers.ValidationError("Each tag needs kind and value.")
        kind = attrs["kind"]
        if kind == TagKind.SPOT:
            key = label = attrs["value"]
        else:
            key, label = normalize_text(attrs["value"])
        if not key or len(label) > TAG_LIMITS[kind]:
            raise serializers.ValidationError(
                {"value": f"Use 1 to {TAG_LIMITS[kind]} characters for this tag."}
            )
        return {"kind": kind, "key": key, "label": label}


class PostWriteSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=PostKind.choices)
    title = TextField(max_length=160)
    body = TextField(max_length=10000)
    tags = TagInputSerializer(many=True)

    def validate_tags(self, values):
        distinct = {(value["kind"], value["key"]): value for value in values}
        if len(distinct) > 10:
            raise serializers.ValidationError("Use at most 10 distinct tags.")
        spot_ids = {key for kind, key in distinct if kind == TagKind.SPOT}
        spots = dict(StudySpot.objects.filter(pk__in=spot_ids).values_list("id", "name"))
        retained = set()
        if self.instance is not None:
            retained = set(
                self.instance.tags.filter(kind=TagKind.SPOT).values_list("key", flat=True)
            )
        if spot_ids - spots.keys() - retained:
            raise serializers.ValidationError("Choose an existing study spot.")
        for value in distinct.values():
            if value["kind"] == TagKind.SPOT and value["key"] in spots:
                value["label"] = spots[value["key"]]
        return list(distinct.values())

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Supply at least one writable field.")
        if "kind" in attrs and attrs["kind"] not in self.context["viewer"].create_kinds:
            raise serializers.ValidationError(
                {"kind": "Your account cannot publish this post kind."}
            )
        return attrs


class BodyWriteSerializer(StrictSerializer):
    body = TextField(max_length=3000)

    def validate(self, attrs):
        if "body" not in attrs:
            raise serializers.ValidationError({"body": "This field is required."})
        return attrs


class ReportWriteSerializer(StrictSerializer):
    reason = TextField(max_length=2000)


class PageQuerySerializer(StrictSerializer):
    limit = serializers.IntegerField(min_value=1, max_value=50, default=20)


class PostQuerySerializer(PageQuerySerializer):
    before = serializers.IntegerField(min_value=1, max_value=MAX_ID, required=False)
    q = TextField(max_length=10000, required=False, allow_blank=True)
    subject = TextField(required=False, allow_blank=True)
    university = TextField(required=False, allow_blank=True)
    spot = TextField(max_length=255, required=False, allow_blank=True)
    kind = serializers.ChoiceField(choices=PostKind.choices, required=False)

    def validate(self, attrs):
        for kind in (TagKind.SUBJECT, TagKind.UNIVERSITY):
            if attrs.get(kind):
                key, label = normalize_text(attrs[kind])
                if len(label) > TAG_LIMITS[kind]:
                    raise serializers.ValidationError({kind: "This tag is too long."})
                attrs[kind] = key
        return attrs


class CommentQuerySerializer(PageQuerySerializer):
    after = serializers.IntegerField(min_value=1, max_value=MAX_ID, required=False)


class TagQuerySerializer(PageQuerySerializer):
    kind = serializers.ChoiceField(choices=TagKind.choices, required=False)
    q = TextField(max_length=255, required=False, allow_blank=True)


def spot_labels(tags) -> dict[str, str]:
    ids = {tag.key for tag in tags if tag.kind == TagKind.SPOT}
    return dict(StudySpot.objects.filter(pk__in=ids).values_list("id", "name")) if ids else {}


def tag_view(tag: Tag, spots: dict[str, str]) -> dict:
    is_spot = tag.kind == TagKind.SPOT
    return {
        "kind": tag.kind,
        "value": tag.key,
        "label": spots.get(tag.key, tag.label) if is_spot else tag.label,
        "available": not is_spot or tag.key in spots,
    }


class AuthoredSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    can_report = serializers.SerializerMethodField()

    def get_author(self, obj):
        return {"kind": obj.author_kind, "name": obj.author_name}

    def get_can_edit(self, obj) -> bool:
        return owns(self.context["viewer"].writer, obj)

    def get_can_delete(self, obj) -> bool:
        return owns(self.context["viewer"].writer, obj)

    def get_can_report(self, obj) -> bool:
        return bool(self.context["viewer"].create_kinds)


class PostSerializer(AuthoredSerializer):
    tags = serializers.SerializerMethodField()
    comment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Post
        fields = (
            "id",
            "kind",
            "title",
            "body",
            "tags",
            "author",
            "created_at",
            "updated_at",
            "comment_count",
            "can_edit",
            "can_delete",
            "can_report",
        )

    def get_tags(self, post):
        return [tag_view(tag, self.context["spots"]) for tag in post.tags.all()]


class CommentSerializer(AuthoredSerializer):
    post_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Comment
        fields = (
            "id",
            "post_id",
            "body",
            "author",
            "created_at",
            "updated_at",
            "can_edit",
            "can_delete",
            "can_report",
        )
