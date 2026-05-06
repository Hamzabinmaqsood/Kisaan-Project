from django.contrib import admin
from .models import CommunityPost, PostLike, PostComment, CommentLike


@admin.register(CommunityPost)
class CommunityPostAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "text", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "text")


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "user", "created_at")
    list_filter = ("created_at",)


@admin.register(PostComment)
class PostCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "user", "text", "created_at")
    list_filter = ("created_at",)


@admin.register(CommentLike)
class CommentLikeAdmin(admin.ModelAdmin):
    list_display = ("id", "comment", "user", "created_at")
    list_filter = ("created_at",)
