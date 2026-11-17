from django.contrib import admin
from django.utils import timezone

from .models import Comment, Post, Report

AUTHOR_FIELDS = (
    "author_account",
    "author_guest_id",
    "author_kind",
    "author_name",
    "created_at",
    "updated_at",
)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "kind", "author_name", "created_at")
    list_filter = ("kind", "author_kind")
    search_fields = ("title", "body", "author_name")
    readonly_fields = AUTHOR_FIELDS

    def has_add_permission(self, request):
        return False


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "author_name", "created_at")
    search_fields = ("body", "author_name")
    readonly_fields = (*AUTHOR_FIELDS, "post")
    list_select_related = ("post",)

    def has_add_permission(self, request):
        return False


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "target_kind", "target_id", "created_at", "reviewed_at")
    list_filter = ("target_kind", "reviewed_at")
    search_fields = ("target_title", "target_body", "reason")
    readonly_fields = tuple(field.name for field in Report._meta.fields)
    actions = ("mark_reviewed",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Mark selected reports reviewed", permissions=["change"])
    def mark_reviewed(self, request, queryset):
        queryset.filter(reviewed_at__isnull=True).update(
            reviewed_at=timezone.now(), reviewed_by=request.user
        )
