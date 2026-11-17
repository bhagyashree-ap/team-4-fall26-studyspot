from django.urls import path

from .views import (
    AccessView,
    CommentDetailView,
    CommentReportView,
    CommentsView,
    PostDetailView,
    PostsView,
    ReportView,
    TagsView,
)

urlpatterns = [
    path("board/access", AccessView.as_view(), name="board-access"),
    path("board/posts", PostsView.as_view(), name="board-posts"),
    path("board/posts/<int:post_id>", PostDetailView.as_view(), name="board-post"),
    path("board/posts/<int:post_id>/comments", CommentsView.as_view(), name="board-comments"),
    path("board/comments/<int:comment_id>", CommentDetailView.as_view(), name="board-comment"),
    path("board/posts/<int:target_id>/reports", ReportView.as_view(), name="board-post-report"),
    path(
        "board/comments/<int:target_id>/reports",
        CommentReportView.as_view(),
        name="board-comment-report",
    ),
    path("board/tags", TagsView.as_view(), name="board-tags"),
]
