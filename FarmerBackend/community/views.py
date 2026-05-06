from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Count, Exists, OuterRef
from rest_framework.permissions import IsAuthenticated
from .models import *
from .serializers import *
from django.db.models import Count
from rest_framework.pagination import PageNumberPagination
User = get_user_model()


class CommunityPostPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class CommentPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50




# ==========================
# POST CREATE + LIST
# ==========================
class CommunityPostView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = CommunityPostSerializer

    def get(self, request):
        user = request.user

        posts = CommunityPost.objects.select_related("user").annotate(
            likes_count=Count("likes", distinct=True),
            comments_count=Count("comments", distinct=True),
            is_liked_by_user=Exists(
                PostLike.objects.filter(
                    post=OuterRef("pk"),
                    user=user
                )
            )
        ).order_by("-id")

        paginator = CommunityPostPagination()
        paginated_posts = paginator.paginate_queryset(posts, request)

        serializer = self.serializer_class(paginated_posts, many=True)
        return paginator.get_paginated_response(serializer.data)
    
    def post(self, request):
        user_id = request.user.id
        if not user_id:
            return Response({"error": "user_id required"}, status=400)

        try:
            user_obj = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            post = serializer.save(user=user_obj)

            data = self.serializer_class(post).data
            if post.image:
                data["image"] = request.build_absolute_uri(post.image.url)
            if post.video:
                data["video"] = request.build_absolute_uri(post.video.url)
            if post.voice:
                data["voice"] = request.build_absolute_uri(post.voice.url)

            return Response(data, status=201)

        return Response(serializer.errors, status=400)


# ==========================
# LIKE / UNLIKE POST
# ==========================
class TogglePostLikeView(APIView):
    
    permission_classes = [IsAuthenticated]  
    def post(self, request, post_id):
        user_id = request.user.id
        if not user_id:
            return Response({"error": "user_id required"}, status=400)

        try:
            user_obj = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        try:
            post = CommunityPost.objects.get(id=post_id)
        except CommunityPost.DoesNotExist:
            return Response({"error": "Post not found"}, status=404)

        like = PostLike.objects.filter(post=post, user=user_obj).first()

        if like:
            like.delete()
            return Response({"message": "Unliked"})
        else:
            PostLike.objects.create(post=post, user=user_obj)
            return Response({"message": "Liked"})


# ==========================
# COMMENT CREATE + LIST
# ==========================
class PostCommentView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PostCommentSerializer

    def get(self, request, post_id):
        user = request.user

        comments = PostComment.objects.select_related("user").filter(
            post_id=post_id
        ).annotate(
            likes_count=Count("likes", distinct=True),
            is_liked_by_user=Exists(
                CommentLike.objects.filter(
                    comment=OuterRef("pk"),
                    user=user
                )
            )
        ).order_by("-id")

        paginator = CommentPagination()
        paginated_comments = paginator.paginate_queryset(comments, request)

        serializer = self.serializer_class(paginated_comments, many=True)
        return paginator.get_paginated_response(serializer.data)
    
    def post(self, request, post_id):
        user_id =request.user.id
        text = request.data.get("text")

        if not user_id:
            return Response({"error": "user_id required"}, status=400)
        if not text:
            return Response({"error": "text required"}, status=400)

        try:
            user_obj = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        try:
            post = CommunityPost.objects.get(id=post_id)
        except CommunityPost.DoesNotExist:
            return Response({"error": "Post not found"}, status=404)

        comment = PostComment.objects.create(post=post, user=user_obj, text=text)
        return Response(self.serializer_class(comment).data, status=201)


# ==========================
# LIKE / UNLIKE COMMENT
# ==========================
class ToggleCommentLikeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, comment_id):
        user_id =request.user.id
        if not user_id:
            return Response({"error": "user_id required"}, status=400)

        try:
            user_obj = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        try:
            comment = PostComment.objects.get(id=comment_id)
        except PostComment.DoesNotExist:
            return Response({"error": "Comment not found"}, status=404)

        like = CommentLike.objects.filter(comment=comment, user=user_obj).first()

        if like:
            like.delete()
            return Response({"message": "Unliked comment"})
        else:
            CommentLike.objects.create(comment=comment, user=user_obj)
            return Response({"message": "Liked comment"})

class PostStatsView(APIView):
    """Return top 5 most liked posts, top 5 most commented posts & graph-ready data"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        most_liked = (
            CommunityPost.objects.annotate(like_count=Count("likes"))
            .order_by("-like_count")[:5]
        )
        most_commented = (
            CommunityPost.objects.annotate(comment_count=Count("comments"))
            .order_by("-comment_count")[:5]
        )
        graph_data = (
            CommunityPost.objects.annotate(
                like_count=Count("likes"),
                comment_count=Count("comments")
            )
            .values("id", "like_count", "comment_count", "created_at")
            .order_by("id")
        )

        return Response({
            "top_5_most_liked": CommunityPostSerializer(most_liked, many=True).data,
            "top_5_most_commented": CommunityPostSerializer(most_commented, many=True).data,
            "graph_data": list(graph_data)
        })
