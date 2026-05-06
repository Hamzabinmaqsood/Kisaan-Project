import uuid
import os
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


def validate_file_size_20mb(file):
    max_size = 20 * 1024 * 1024
    if file.size > max_size:
        raise ValidationError("File size must be <= 20MB")


def post_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()

    # folder: community/user_12/
    folder = f"community/user_{instance.user.id}"

    # file: post_<postid>_<random>.ext (safe)
    return f"{folder}/{uuid.uuid4()}{ext}"


class CommunityPost(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_posts"
    )

    text = models.TextField(blank=True, null=True)

    image = models.ImageField(upload_to=post_upload_path, blank=True, null=True, validators=[validate_file_size_20mb])
    video = models.FileField(upload_to=post_upload_path, blank=True, null=True, validators=[validate_file_size_20mb])
    voice = models.FileField(upload_to=post_upload_path, blank=True, null=True, validators=[validate_file_size_20mb])

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Post {self.id} by {self.user}"


class PostLike(models.Model):
    post = models.ForeignKey(
        CommunityPost,
        on_delete=models.CASCADE,
        related_name="likes"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="post_likes"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("post", "user")

    def __str__(self):
        return f"{self.user} liked post {self.post.id}"


class PostComment(models.Model):
    post = models.ForeignKey(
        CommunityPost,
        on_delete=models.CASCADE,
        related_name="comments"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="post_comments"
    )

    text = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment {self.id} on Post {self.post.id}"


class CommentLike(models.Model):
    comment = models.ForeignKey(
        PostComment,
        on_delete=models.CASCADE,
        related_name="likes"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comment_likes"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("comment", "user")

    def __str__(self):
        return f"{self.user} liked comment {self.comment.id}"
