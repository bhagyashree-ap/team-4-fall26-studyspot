from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import Auth0Authentication
from communities.views import CommunitySessionAuthentication

from .identity import author_stamp, owns, reporter_stamp, viewer_for
from .models import Comment, Post, PostTag, Report, Tag, TagKind
from .serializers import (
    BodyWriteSerializer,
    CommentQuerySerializer,
    CommentSerializer,
    PostQuerySerializer,
    PostSerializer,
    PostWriteSerializer,
    ReportWriteSerializer,
    TagQuerySerializer,
    normalize_text,
    spot_labels,
    tag_view,
)


def readable_posts():
    return Post.objects.annotate(comment_count=Count("comments")).prefetch_related("tags")


def replace_tags(post: Post, values: list[dict]) -> None:
    tags = []
    for value in sorted(values, key=lambda tag: (tag["kind"], tag["key"])):
        tag, _ = Tag.objects.get_or_create(
            kind=value["kind"],
            key=value["key"],
            defaults={"label": value.get("label", value["key"])},
        )
        tags.append(tag)
    PostTag.objects.filter(post=post).delete()
    PostTag.objects.bulk_create([PostTag(post=post, tag=tag) for tag in tags])


class BoardView(APIView):
    authentication_classes = [Auth0Authentication, CommunitySessionAuthentication]
    establish_guest = False

    def initial(self, request: Request, *args, **kwargs):
        request.board_session_user = request._request.user
        get_token(request)
        super().initial(request, *args, **kwargs)
        self.viewer = viewer_for(
            request,
            establish_guest=self.establish_guest
            or request.method not in {"GET", "HEAD", "OPTIONS"},
        )

    def require_owner(self, authored):
        writer = self.viewer.require_writer()
        if not owns(writer, authored):
            raise PermissionDenied("Only the author can change this content.")
        return writer

    def serialize_posts(self, posts):
        tags = [tag for post in posts for tag in post.tags.all()]
        return PostSerializer(
            posts, many=True, context={"viewer": self.viewer, "spots": spot_labels(tags)}
        ).data

    def serialize_post(self, post_id: int):
        post = get_object_or_404(readable_posts(), pk=post_id)
        return self.serialize_posts([post])[0]

    def serialize_comment(self, comment: Comment):
        return CommentSerializer(comment, context={"viewer": self.viewer}).data


class AccessView(BoardView):
    establish_guest = True

    def get(self, request: Request):
        return Response(
            {
                "viewer": self.viewer.kind,
                "guest_access": settings.CHAT_GUEST_ACCESS,
                "create_kinds": self.viewer.create_kinds,
                "can_comment": bool(self.viewer.create_kinds),
                "can_report": bool(self.viewer.create_kinds),
                "limits": {"title": 160, "body": 10000, "comment": 3000, "reason": 2000},
            }
        )


class PostsView(BoardView):
    def get(self, request: Request):
        query = PostQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        posts = readable_posts()
        if data.get("q"):
            posts = posts.filter(Q(title__icontains=data["q"]) | Q(body__icontains=data["q"]))
        if data.get("kind"):
            posts = posts.filter(kind=data["kind"])
        for kind in TagKind.values:
            if data.get(kind):
                links = PostTag.objects.filter(tag__kind=kind, tag__key=data[kind])
                posts = posts.filter(pk__in=links.values("post_id"))
        if "before" in data:
            posts = posts.filter(pk__lt=data["before"])
        limit = data["limit"]
        page = list(posts.order_by("-id")[: limit + 1])
        return Response(
            {"items": self.serialize_posts(page[:limit]), "has_more": len(page) > limit}
        )

    @transaction.atomic
    def post(self, request: Request):
        writer = self.viewer.require_writer()
        serializer = PostWriteSerializer(data=request.data, context={"viewer": self.viewer})
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        tags = data.pop("tags")
        post = Post.objects.create(**data, **author_stamp(writer))
        replace_tags(post, tags)
        return Response(self.serialize_post(post.pk), status=201)


class PostDetailView(BoardView):
    def get(self, request: Request, post_id: int):
        return Response(self.serialize_post(post_id))

    @transaction.atomic
    def patch(self, request: Request, post_id: int):
        post = get_object_or_404(Post.objects.select_for_update(), pk=post_id)
        self.require_owner(post)
        serializer = PostWriteSerializer(
            post, data=request.data, partial=True, context={"viewer": self.viewer}
        )
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        tags = data.pop("tags", None)
        for field, value in data.items():
            setattr(post, field, value)
        post.save(update_fields=[*data, "updated_at"])
        if tags is not None:
            replace_tags(post, tags)
        return Response(self.serialize_post(post.pk))

    @transaction.atomic
    def delete(self, request: Request, post_id: int):
        post = get_object_or_404(Post.objects.select_for_update(), pk=post_id)
        self.require_owner(post)
        post.delete()
        return Response(status=204)


class CommentsView(BoardView):
    def get(self, request: Request, post_id: int):
        get_object_or_404(Post, pk=post_id)
        query = CommentQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        comments = Comment.objects.filter(post_id=post_id)
        if "after" in data:
            comments = comments.filter(pk__gt=data["after"])
        limit = data["limit"]
        page = list(comments.order_by("id")[: limit + 1])
        return Response(
            {
                "items": CommentSerializer(
                    page[:limit], many=True, context={"viewer": self.viewer}
                ).data,
                "has_more": len(page) > limit,
            }
        )

    @transaction.atomic
    def post(self, request: Request, post_id: int):
        writer = self.viewer.require_writer()
        serializer = BodyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # The parent lock keeps its deletion from racing comment insertion.
        post = get_object_or_404(Post.objects.select_for_update(), pk=post_id)
        comment = Comment.objects.create(
            post=post, **serializer.validated_data, **author_stamp(writer)
        )
        return Response(self.serialize_comment(comment), status=201)


class CommentDetailView(BoardView):
    @transaction.atomic
    def patch(self, request: Request, comment_id: int):
        comment = get_object_or_404(Comment.objects.select_for_update(), pk=comment_id)
        self.require_owner(comment)
        serializer = BodyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment.body = serializer.validated_data["body"]
        comment.save(update_fields=["body", "updated_at"])
        return Response(self.serialize_comment(comment))

    @transaction.atomic
    def delete(self, request: Request, comment_id: int):
        comment = get_object_or_404(Comment.objects.select_for_update(), pk=comment_id)
        self.require_owner(comment)
        comment.delete()
        return Response(status=204)


class TagsView(BoardView):
    def get(self, request: Request):
        query = TagQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        tags = Tag.objects.annotate(post_count=Count("post_links")).filter(post_count__gt=0)
        if "kind" in data:
            tags = tags.filter(kind=data["kind"])
        if data.get("q"):
            key, _ = normalize_text(data["q"])
            tags = tags.filter(Q(key__contains=key) | Q(label__icontains=data["q"]))
        page = list(tags.order_by("kind", "key", "id")[: data["limit"]])
        spots = spot_labels(page)
        return Response(
            {"items": [{**tag_view(tag, spots), "post_count": tag.post_count} for tag in page]}
        )


class ReportView(BoardView):
    target_model: type[Post] | type[Comment] = Post
    target_kind = Report.TargetKind.POST

    @transaction.atomic
    def post(self, request: Request, target_id: int):
        writer = self.viewer.require_writer()
        serializer = ReportWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Capture evidence before an edit or deletion; report fields retain it afterward.
        target = get_object_or_404(self.target_model.objects.select_for_update(), pk=target_id)
        reporter = reporter_stamp(writer)
        reporter_kind = reporter.pop("reporter_kind")
        reporter_name = reporter.pop("reporter_name")
        _, created = Report.objects.get_or_create(
            target_kind=self.target_kind,
            target_id=target.pk,
            **reporter,
            defaults={
                "reporter_kind": reporter_kind,
                "reporter_name": reporter_name,
                "reason": serializer.validated_data["reason"],
                "target_title": target.title if isinstance(target, Post) else "",
                "target_body": target.body,
                "target_author_kind": target.author_kind,
                "target_author_name": target.author_name,
            },
        )
        return Response({"reported": True}, status=201 if created else 200)


class CommentReportView(ReportView):
    target_model = Comment
    target_kind = Report.TargetKind.COMMENT
