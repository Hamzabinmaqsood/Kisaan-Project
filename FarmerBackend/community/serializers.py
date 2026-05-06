from rest_framework import serializers
from .models import CommunityPost, PostComment


class CommunityPostSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)

    likes_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    is_liked_by_user = serializers.BooleanField(read_only=True)

    class Meta:
        model = CommunityPost
        fields = [
            "id",
            "user_id",
            "username",
            "text",
            "image",
            "video",
            "voice",
            "likes_count",
            "comments_count",
            "is_liked_by_user",
            "created_at",
        ]
        read_only_fields = fields
        
           
class PostCommentSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)

    likes_count = serializers.IntegerField(read_only=True)
    is_liked_by_user = serializers.BooleanField(read_only=True)

    class Meta:
        model = PostComment
        fields = [
            "id",
            "post",
            "user_id",
            "username",
            "text",
            "likes_count",
            "is_liked_by_user",
            "created_at"
        ]
        read_only_fields = fields