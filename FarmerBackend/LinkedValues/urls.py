from django.urls import path
from .views import district_list_create, district_detail

urlpatterns = [
    path('districts/', district_list_create),
    path('districts/<int:pk>/', district_detail),
]