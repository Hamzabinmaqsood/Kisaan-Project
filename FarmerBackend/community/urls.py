from django.urls import path
from .views import (
    CommunityPostView,
    TogglePostLikeView,
    PostCommentView,
    ToggleCommentLikeView
)
from .views import *

urlpatterns = [
    path("posts/", CommunityPostView.as_view(), name="community-posts"),

    path("posts/<int:post_id>/like/", TogglePostLikeView.as_view(), name="post-like"),

    path("posts/<int:post_id>/comments/", PostCommentView.as_view(), name="post-comments"),

    path("comments/<int:comment_id>/like/", ToggleCommentLikeView.as_view(), name="comment-like"),
    path("stats/", PostStatsView.as_view(), name="post_stats"),
]
