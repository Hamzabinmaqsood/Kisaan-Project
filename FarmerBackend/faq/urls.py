from django.urls import path
from .views import CropListAPIView, CropFAQAPIView

urlpatterns = [
    path("crops/", CropListAPIView.as_view(), name="crop-list"),
    path("crops/<int:crop_id>/faqs/", CropFAQAPIView.as_view(), name="crop-faqs"),
]