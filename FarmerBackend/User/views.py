from rest_framework import generics, permissions
from .models import*
from .serializers import *
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.authtoken.models import Token 
from django.shortcuts import get_object_or_404
from collections import Counter
import json
import base64
import numpy as np
from PIL import Image
from io import BytesIO
from django.conf import settings
import base64
import numpy as np
from PIL import Image
from io import BytesIO
from collections import defaultdict
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from django.conf import settings

from sentinelhub import BBox, CRS

from .models import Farms
from .sentinel import get_sentinel_image


class FarmSatelliteView(APIView):

    def post(self, request):
        farm_id = request.data.get("farm_id")

        if not farm_id:
            return Response({"error": "farm_id is required"}, status=400)

        try:
            farm = Farms.objects.get(id=farm_id)
            print(f"Fetching satellite image for farm: {farm} (ID: {farm.id})")
            # -----------------------------------------
            # 1. Convert string → list (if needed)
            # -----------------------------------------
            coords = farm.bbox
            print(f"Fetching satellite image for farm: {coords}")

            coords = farm.bbox

            # -----------------------------------------
            # FIX: convert string → list
            # -----------------------------------------
            if isinstance(coords, str):
                coords = json.loads(coords)

            print(f"DEBUG coords type: {type(coords)}")
            print(f"DEBUG coords: {coords}")

            # -----------------------------------------
            # NOW SAFE TO LOOP
            # -----------------------------------------
            lats = [c[0] for c in coords]
            lons = [c[1] for c in coords]

            min_lat, max_lat = min(lats), max(lats)
            min_lon, max_lon = min(lons), max(lons)

            bbox_coords = [min_lon, min_lat, max_lon, max_lat]

            print(f"DEBUG bbox_coords: {bbox_coords}")

            
            # -----------------------------------------
            # 3. Fetch satellite image
            # -----------------------------------------
            image, date = get_sentinel_image(
                bbox_coords,
                settings.SENTINEL_HUB["CLIENT_ID"],
                settings.SENTINEL_HUB["CLIENT_SECRET"]
            )

            print(f"[DEBUG] Check saved debug images at: /tmp/sentinel_debug/")
            print(f"[DEBUG] image min={image.min()} max={image.max()} mean={image.mean():.2f}")

            # -----------------------------------------
            # 4. Convert image → base64
            # -----------------------------------------
            img = Image.fromarray(np.uint8(image))
            buffer = BytesIO()
            img.save(buffer, format="PNG")

            image_base64 = base64.b64encode(buffer.getvalue()).decode()

            return Response({
                "farm_id": farm.id,
                "image": image_base64,
                "date": date
            })

        except Farms.DoesNotExist:
            return Response({"error": "Farm not found"}, status=404)

        except Exception as e:
            return Response({"error": str(e)}, status=500)
        

class UpdateSectionNameAPI(APIView):

    def post(self, request):
        serializer = UpdateSectionSerializer(data=request.data)

        if serializer.is_valid():
            cnic = serializer.validated_data['cnic']
            section_name = serializer.validated_data['section_name']

            try:
                user = CustomUser.objects.get(cnic=cnic)
                user.section_name = section_name
                user.save()

                return Response({
                    "message": "Section name updated successfully",
                    "cnic": user.cnic,
                    "section_name": user.section_name
                }, status=status.HTTP_200_OK)

            except CustomUser.DoesNotExist:
                return Response({
                    "error": "User with this CNIC does not exist"
                }, status=status.HTTP_404_NOT_FOUND)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
# Followers APIs
class UserFollwersListCreateView(generics.ListCreateAPIView):
    queryset = UserFollwers.objects.all()
    serializer_class = UserFollwersSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class UserFollwersRetrieveUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = UserFollwers.objects.all()
    serializer_class = UserFollwersSerializer
    permission_classes = [permissions.IsAuthenticated]

# Following APIs
class UserFollowingListCreateView(generics.ListCreateAPIView):
    queryset = UserFollwing.objects.all()
    serializer_class = UserFollwingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class UserFollowingRetrieveUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = UserFollwing.objects.all()
    serializer_class = UserFollwingSerializer
    permission_classes = [permissions.IsAuthenticated]


class UserProfileView(generics.RetrieveAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'  

class LoginAPIView(APIView):
    """
    Login API that authenticates user via CNIC and password
    """
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']

        # Create or get token
        token, created = Token.objects.get_or_create(user=user)

        return Response({
            "message": "Login successful",
            "token": token.key,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "cnic": user.cnic,
                "mobile": user.mobile_number,
                "role": user.role.name
            }
        }, status=status.HTTP_200_OK)
    

# LIST + CREATE
class FarmsListCreateView(generics.ListCreateAPIView):

    serializer_class = FarmsSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # show only farms created by logged-in user
        return Farms.objects.filter(created_by=self.request.user).order_by("-id")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


# RETRIEVE + UPDATE + DELETE
class FarmsDetailView(generics.RetrieveUpdateDestroyAPIView):

    serializer_class = FarmsSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # security: user can access only own farms
        return Farms.objects.filter(created_by=self.request.user)
    

class FarmerListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        farmers = CustomUser.objects.filter(role__name="Farmer")
        serializer = FarmerListSerializer(farmers, many=True)
        return Response(serializer.data)
    
class UserFarmsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        user = get_object_or_404(CustomUser, id=user_id)
        farms = Farms.objects.filter(created_by=user)

        serializer = FarmSerializer(farms, many=True)
        return Response(serializer.data)
    


class SignupAPIView(APIView):

    def post(self, request):
        serializer = SignupSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "message": "User created successfully",
                "user_id": user.id,
                "username": user.username,
                "mobile_number": user.mobile_number
            }, status=status.HTTP_201_CREATED)

        return Response({
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    


# ---------------- ADD CROP ----------------

class UpsertCropAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        If user already has crops entry with the same ID, update it.
        Otherwise, create a new entry.
        """
        user = request.user
        data = request.data.copy()
        data['user'] = user.id

        crop_id = data.get("id")  # optional: if client sends id for update

        if crop_id:
            # Try to fetch existing crop
            crop = CropDetails.objects.filter(id=crop_id, user=user).first()
            if crop:
                serializer = CropDetailsSerializer(crop, data=data, partial=True)
                action = "updated"
            else:
                serializer = CropDetailsSerializer(data=data)
                action = "added"
        else:
            # No ID sent → check if user has any crops entry
            crop = CropDetails.objects.filter(user=user).first()
            if crop:
                serializer = CropDetailsSerializer(crop, data=data, partial=True)
                action = "updated"
            else:
                serializer = CropDetailsSerializer(data=data)
                action = "added"

        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": f"Crops {action} successfully",
                "data": serializer.data
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

# ---------------- GET CROPS ----------------

class GetUserFirstCropAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Returns the first crop entry for the current user
        with crop_name as a list.
        """
        user = request.user

        # Get first crop entry
        crop = CropDetails.objects.filter(user=user).first()

        if not crop:
            return Response({"message": "No crops found for this user"}, status=404)

        # Split comma-separated crop names
        crop_list = [c.strip() for c in crop.crop_name.split(",") if c.strip()]

        return Response({
            "id": crop.id,
            "user": crop.user.id,
            "crop_name": crop_list
        })
    
class MostCommonCropsAPIView(APIView):

    def get(self, request):
        crop_entries = CropDetails.objects.values_list("crop_name", flat=True)

        all_crops = []
        for entry in crop_entries:
            crops = [c.strip().lower() for c in entry.split(",") if c.strip()]
            all_crops.extend(crops)

        if not all_crops:
            return Response({"most_common_crops": []})

        crop_count = Counter(all_crops)

        # Get the maximum count
        max_count = max(crop_count.values())

        # Filter only crops that have this maximum count
        most_common = [
            {"crop": crop, "count": count}
            for crop, count in crop_count.items()
            if count == max_count
        ]

        return Response({"most_common_crops": most_common})


class UserDashboardAPIView(APIView):

    def get(self, request):
        users = CustomUser.objects.select_related('role', 'user_creator').all()

        grouped_data = defaultdict(list)
        no_creator_users = []

        for user in users:
            data = {
                "username": user.username,
                "cnic": user.cnic,
                "section_name": user.section_name,
                "role_name": user.role.name if user.role else None,
                "created_at": user.created_at
            }

            if user.user_creator:
                creator_key = f"{user.user_creator.id}-{user.user_creator.username}"
                grouped_data[creator_key].append(data)
            else:
                no_creator_users.append(data)

        # Format response
        response_data = []

        for creator, user_list in grouped_data.items():
            creator_id, creator_name = creator.split('-')

            response_data.append({
                "creator_id": creator_id,
                "creator_name": creator_name,
                "total_users": len(user_list),
                "users": user_list
            })

        return Response({
            "creators": response_data,
            "no_creator": {
                "total_users": len(no_creator_users),
                "users": no_creator_users
            }
        })