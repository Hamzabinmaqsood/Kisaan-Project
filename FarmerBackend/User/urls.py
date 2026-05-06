from django.urls import path
from .views import *

urlpatterns = [
    # Followers
    path('followers/', UserFollwersListCreateView.as_view(), name='followers-list-create'),
    path('followers/<int:pk>/', UserFollwersRetrieveUpdateDeleteView.as_view(), name='followers-detail'),
    
    # Following
    path('following/', UserFollowingListCreateView.as_view(), name='following-list-create'),
    path('following/<int:pk>/', UserFollowingRetrieveUpdateDeleteView.as_view(), name='following-detail'),

    # User Profile
    path('profile/<int:id>/', UserProfileView.as_view(), name='user-profile'),
# urls.py
  path("signup/", SignupAPIView.as_view(), name="signup"),
  path("farmers/", FarmerListAPIView.as_view(), name="farmer-list"),
  path("user-farms/<int:user_id>/", UserFarmsAPIView.as_view(), name="user-farms"),
  path("farms/", FarmsListCreateView.as_view(), name="farms-list-create"),
  path("farms/<int:pk>/", FarmsDetailView.as_view(), name="farms-detail"),
    path('user-dashboard/', UserDashboardAPIView.as_view()),
    path("crops/add/", UpsertCropAPIView.as_view()),
    path("crops/get-crops/", GetUserFirstCropAPIView.as_view()),
    path("crops/most-common/", MostCommonCropsAPIView.as_view()),
    path('update-section/', UpdateSectionNameAPI.as_view(), name='update-section'),
   path("farm/satellite/", FarmSatelliteView.as_view()),
]
