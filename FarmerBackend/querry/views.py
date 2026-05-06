from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db import transaction

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from .models import *
from .serializers import *

User = get_user_model()


# -----------------------------
# PAGINATION CLASS
# -----------------------------
class StandardPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100



# =========================================================
# 1) UPLOAD QUERY
# POST: /query/upload/
# =========================================================
class UploadQueryView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @transaction.atomic
    def post(self, request):
        user = request.user
        serializer = MediaMessageSerializer(data=request.data)

        if serializer.is_valid():
            query_obj = serializer.save(user=user)

            # =========================================
            # AUTO ASSIGN TO ADMIN (Sticky + Balanced)
            # =========================================

            selected_admin = None

            # 1) Check if this user has been assigned to someone before
            previous_assignment = AssignedQuery.objects.filter(
                query__user=user
            ).select_related("user").order_by("-assigned_at").first()

            if previous_assignment and previous_assignment.user.is_active:
                # Stick to the same response team member
                selected_admin = previous_assignment.user

            else:
                # 2) New user — use balanced assignment
                admins = User.objects.filter(
                    role__name="Response_Team",
                    is_active=True
                ).annotate(
                    total_assigned=Count("assigned_queries", distinct=True)
                ).order_by("total_assigned", "id")

                if admins.exists():
                    selected_admin = admins.first()

            if selected_admin:
                AssignedQuery.objects.create(
                    user=selected_admin,
                    query=query_obj
                )

            # =========================================

            data = MediaMessageSerializer(
                query_obj,
                context={"request": request}
            ).data

            if query_obj.image:
                data["image"] = request.build_absolute_uri(query_obj.image.url)
            if query_obj.video:
                data["video"] = request.build_absolute_uri(query_obj.video.url)
            if query_obj.voice:
                data["voice"] = request.build_absolute_uri(query_obj.voice.url)

            return Response(data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# =========================================================
# 2) SEND RESPONSE
# POST: /query/respond/<query_id>/
# =========================================================
class SendResponseView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, query_id):

        user = request.user

        # restrict access to response team
        if not user.is_superuser and user.role.name != "Response_Team":
            return Response(
                {"error": "Only response team can reply"},
                status=status.HTTP_403_FORBIDDEN
            )

        # get query
        try:
            query_obj = MediaMessage.objects.get(id=query_id)
        except MediaMessage.DoesNotExist:
            return Response(
                {"error": "Query not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # prevent duplicate responses
        if query_obj.is_done:
            return Response(
                {"error": "Query already answered"},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = MediaResponseSerializer(data=request.data)

        if serializer.is_valid():
            obj = serializer.save(
                query=query_obj,
                responder=user
            )

            # mark done
            query_obj.is_done = True
            query_obj.save(update_fields=["is_done"])

            data = MediaResponseSerializer(
                obj,
                context={"request": request}
            ).data

            # attach full media URLs
            if obj.image:
                data["image"] = request.build_absolute_uri(obj.image.url)
            if obj.video:
                data["video"] = request.build_absolute_uri(obj.video.url)
            if obj.voice:
                data["voice"] = request.build_absolute_uri(obj.voice.url)

            return Response(data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# =========================================================
# 3) LIST QUERIES
# GET: /query/list/?status=pending|done
# =========================================================
class QueryListView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get(self, request):

        user = request.user
        status_filter = request.GET.get("status", "").lower().strip()

        # =========================================
        # ROLE BASED QUERY FILTERING
        # =========================================
        if user.role.name == "SuperAdmin":
            qs = MediaMessage.objects.all()

        elif user.role.name == "Response_Team":
            qs = MediaMessage.objects.filter(
                assignment__user=user
            )

        elif user.role.name == "Farmer":
            qs = MediaMessage.objects.filter(user=user)

        else:
            qs = MediaMessage.objects.filter(user=user)

        # =========================================
        # STATUS FILTER
        # =========================================
        if status_filter == "pending":
            qs = qs.filter(is_done=False)
        elif status_filter == "done":
            qs = qs.filter(is_done=True)

        qs = qs.order_by("-id")

        # =========================================
        # PAGINATION
        # =========================================
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)

        serializer = MediaMessageSerializer(
            page,
            many=True,
            context={"request": request}
        )

        return paginator.get_paginated_response(serializer.data)

# =========================================================
# 4) GET RESPONSES BY QUERY
# GET: /query/<query_id>/responses/
# =========================================================
class MediaResponseByQueryAPIView(ListAPIView):
    serializer_class = GET_RESPONSE_MediaResponseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        query_id = self.kwargs["query_id"]
        return MediaResponse.objects.filter(
            query_id=query_id
        ).order_by("created_at")