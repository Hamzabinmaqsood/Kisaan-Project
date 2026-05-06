from rest_framework.pagination import PageNumberPagination
from rest_framework.generics import ListAPIView
from .models import FAQ
from .serializers import FAQSerializer, CropSerializer
from CropsRecomendations.models import CropType


class FAQPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


# 1️⃣ Crop List API
class CropListAPIView(ListAPIView):
    queryset = CropType.objects.all().order_by("name")
    serializer_class = CropSerializer
    pagination_class = None


# 2️⃣ Crop FAQ API (Grouped)
class CropFAQAPIView(ListAPIView):
    serializer_class = FAQSerializer
    pagination_class = FAQPagination

    def get_queryset(self):
        crop_id = self.kwargs.get("crop_id")

        return FAQ.objects.select_related(
            "crop",
            "crop_season"
        ).prefetch_related(
            "items"
        ).filter(
            crop_id=crop_id
        ).order_by("-created_at")