from django.urls import path
from .views import *

urlpatterns = [
    path("upload/", UploadQueryView.as_view(), name="upload_query"),
    path("respond/<int:query_id>/", SendResponseView.as_view(), name="send_response"),
    path("list/", QueryListView.as_view(), name="query_list"),
    path("query-response/<int:query_id>/",MediaResponseByQueryAPIView.as_view(),name="query-response-list"),
]