from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from django.db import transaction
from django.contrib.auth import get_user_model

from .services import ReportGenerationService
from .serializers import ReportsSerializer, ReportResponseSerializer
from .models import Reports
from User.models import CustomUser

import logging

logger = logging.getLogger(__name__)
User = get_user_model()


# ── Pagination ─────────────────────────────────────────────────────────────

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


# ── List reports for a user ────────────────────────────────────────────────

class UserReportsAPIView(APIView):
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAuthenticated]
    def get(self, request, user_id):
        try:
            user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        report_type = request.query_params.get("report_type")   # optional filter
        qs = Reports.objects.filter(user=user).order_by("-generated_at")
        if report_type in ("farmer", "agro"):
            qs = qs.filter(report_type=report_type)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        serializer = ReportsSerializer(page, many=True)

        return paginator.get_paginated_response({
            "user_id":  user.id,
            "username": user.username,
            "results":  serializer.data,
        })


# ── Shared report-generation logic ─────────────────────────────────────────

def _run_report(request, report_type: str):
    """
    Shared implementation for both farmer and agro report endpoints.

    Expected payload:
    {
        "user_id":          <int>,
        "farm_id":          <int>,
        "force_regenerate": <bool>   (optional, default false)
    }
    """
    user_obj = None   # keep in scope for fallback

    try:
        user_id  = request.data.get("user_id")
        farm_id  = request.data.get("farm_id")
        force    = request.data.get("force_regenerate", False)

        if not farm_id:
            return Response({"error": "farm_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not user_id:
            return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_obj = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        print(f"User {user_obj.username} ({user_obj.id}) requested a {report_type} report for farm {farm_id} (force={force})")
        service = ReportGenerationService(user=user_obj, farm_id=farm_id, report_type=report_type)

        # ── Cache check ────────────────────────────────────────────────
        if not force:
            existing = service.get_todays_successful_report()
            if existing:
                serializer = ReportResponseSerializer(existing, context={"request": request})
                return Response({**serializer.data, "cached": True}, status=status.HTTP_200_OK)

        # ── Generate ───────────────────────────────────────────────────
        with transaction.atomic():
            report = service.generate()

        serializer = ReportResponseSerializer(report, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.error(f"[{report_type}] Report generation failed: {e}", exc_info=True)

        # ── Fallback ───────────────────────────────────────────────────
        try:
            if user_obj is None:
                raise RuntimeError("user_obj not available for fallback")
            svc_fallback = ReportGenerationService(
                user=user_obj, farm_id=request.data.get("farm_id"), report_type=report_type
            )
            report = svc_fallback.generate_fallback()
            serializer = ReportResponseSerializer(report, context={"request": request})
            return Response(
                {**serializer.data, "warning": "Report generated with default content due to processing errors"},
                status=status.HTTP_201_CREATED,
            )
        except Exception as fallback_err:
            logger.critical(f"[{report_type}] Fallback failed: {fallback_err}", exc_info=True)
            return Response(
                {"error": "Report generation failed completely"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_farmer_report(request):
    """
    Generate a farmer-facing report.

    Uses a single index per crop stage:
      - Pre Planting (0-30 days)  → MSAVI
      - Vegetative   (30-65 days) → NDVI
      - Flowering    (65-95 days) → NDVI
      - Maturity     (95-135 days)→ NDVI

    Payload: { "user_id": int, "farm_id": int, "force_regenerate": bool }
    """
    return _run_report(request, report_type="farmer")


# ── Agro report endpoint  POST /api/reports/agro/ ─────────────────────────

@api_view(["POST"])
# @permission_classes([IsAuthenticated])
def generate_agro_report(request):
    """
    Generate a detailed agronomist report.

    Uses multiple indices per crop stage:
      - Pre Planting (0-30 days)  → MSAVI + NDVI
      - Vegetative   (30-65 days) → NDVI + NDMI + NDRE
      - Flowering    (65-95 days) → NDVI + NDMI + NDRE
      - Maturity     (95-135 days)→ NDVI + ReCL

    Payload: { "user_id": int, "farm_id": int, "force_regenerate": bool }
    """
    return _run_report(request, report_type="agro")


# ── Legacy endpoint (kept for backwards compatibility) ─────────────────────

@api_view(["POST"])
def generate_report(request):
    """
    Legacy endpoint — routes to farmer report by default.
    Pass "report_type": "agro" in the payload to get an agro report.
    """
    report_type = "farmer"
    if report_type not in ("farmer", "agro"):
        return Response(
            {"error": "report_type must be 'farmer' or 'agro'"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return _run_report(request, report_type=report_type)