from django.urls import path
from .views import *

urlpatterns = [
    path("ajax/get-crops/", get_crops_by_season, name="get-crops"),
     path("crops/", crops_grouped_by_season, name="crops-grouped"),

]