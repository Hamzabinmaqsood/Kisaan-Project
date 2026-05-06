"""
URL Configuration for voice_api app with NDVI support
"""

from django.urls import path
from .views import GenerateWithNDVIView

urlpatterns = [
    path('generate-with-ndvi/', GenerateWithNDVIView.as_view(), name='generate-with-ndvi'),
]
