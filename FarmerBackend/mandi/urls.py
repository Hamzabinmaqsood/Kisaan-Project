from django.urls import path
from .views import MandiDataView

urlpatterns = [
    path("data/", MandiDataView.as_view()),
]
