from django.urls import path
from .views import (
    UserReportsAPIView,
    generate_farmer_report,
    generate_agro_report,
    generate_report,
)

urlpatterns = [
    # ── Get all reports for a user ─────────────────────────────
    path("user/<int:user_id>/", UserReportsAPIView.as_view(), name="user-reports"),

    # ── Generate reports ──────────────────────────────────────
    path("farmer/", generate_farmer_report, name="generate-farmer-report"),
    path("agro/", generate_agro_report, name="generate-agro-report"),

    # ── Legacy endpoint ───────────────────────────────────────
    path("generate/", generate_report, name="generate-report"),
]