from rest_framework import serializers
from .models import *
from django.contrib.auth import authenticate
from rest_framework.validators import UniqueValidator
from django.db import IntegrityError

class UpdateSectionSerializer(serializers.Serializer):
    cnic = serializers.CharField(max_length=13)
    section_name = serializers.CharField(max_length=50)

class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'cnic', 'email']


class UserFollwersSerializer(serializers.ModelSerializer):
    user = CustomUserSerializer(read_only=True)
    follower = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all(), many=True)

    class Meta:
        model = UserFollwers
        fields = ['id', 'user', 'follower', 'created_at']


class UserFollwingSerializer(serializers.ModelSerializer):
    user = CustomUserSerializer(read_only=True)
    following = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all(), many=True)

    class Meta:
        model = UserFollwing
        fields = ['id', 'user', 'following', 'created_at']

class UserProfileSerializer(serializers.ModelSerializer):
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    role = serializers.CharField(source='role.name', read_only=True)


    class Meta:
        model = CustomUser
        fields = [
            'id',
            'username',
            'email',
            'cnic',
            'mobile_number',
            'role',
            'followers_count',
            'following_count',
        ]

    def get_followers_count(self, obj):
        return UserFollwers.objects.filter(follower=obj).count()

    def get_following_count(self, obj):
        return UserFollwing.objects.filter(user=obj).first().following.count() \
            if UserFollwing.objects.filter(user=obj).exists() else 0

class LoginSerializer(serializers.Serializer):
    cnic = serializers.CharField(max_length=13)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        cnic = data.get('cnic')
        password = data.get('password')

        if cnic and password:
            user = authenticate(username=cnic, password=password)
            if user is None:
                raise serializers.ValidationError("Invalid CNIC or password")
            if not user.is_active:
                raise serializers.ValidationError("User is inactive")
        else:
            raise serializers.ValidationError("CNIC and password are required")

        data['user'] = user
        return data
    
class FarmsSerializer(serializers.ModelSerializer):

    created_by = serializers.ReadOnlyField(source="created_by.id")
    created_by_username = serializers.ReadOnlyField(source="created_by.username")

    class Meta:
        model = Farms
        fields = [
            "id",
            "farm_name",
            "bbox",
            "total_acres",
            "crop_season",
            "crop",
            "sowing_date",
            "district",
            "created_by",
            "created_by_username",
            "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]


class FarmerListSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ["id", "username", "cnic","section_name"]



class FarmSerializer(serializers.ModelSerializer):
    crop_name = serializers.CharField(source="crop.name", read_only=True)
    season_name = serializers.CharField(source="crop_season.name", read_only=True)
    district_name = serializers.CharField(source="district.name", read_only=True)

    class Meta:
        model = Farms
        fields = [
            "id",
            "farm_name",
            "total_acres",
            "bbox",
            "created_at",

            # FK IDs
            "crop",
            "crop_season",
            "district",

            # FK Names
            "crop_name",
            "season_name",
            "district_name",
	    "sowing_date"
        ]


class SignupSerializer(serializers.ModelSerializer):
    username = serializers.CharField(required=True)
    mobile_number = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, min_length=6, required=True)

    class Meta:
        model = CustomUser
        fields = ["id", "username",  "mobile_number", "password"]

   

    # ? Validate Mobile (must be 11 digits)
    def validate_mobile_number(self, value):
        if not value.isdigit() or len(value) != 11:
            raise serializers.ValidationError("Mobile number must be exactly 11 digits.")
        return value

    # ? Custom create method
    def create(self, validated_data):
        password = validated_data.pop("password")
        role, _ = Role.objects.get_or_create(name="Farmer")

        try:
            user = CustomUser(**validated_data)
            user.role = role
            user.set_password(password)
            user.save()
            return user
        except IntegrityError:
            raise serializers.ValidationError({
                "mobile_number": "A user with this mobile_number already exists."
            })



class CropDetailsSerializer(serializers.ModelSerializer):

    class Meta:
        model = CropDetails
        fields = ["id", "crop_name", "user"]

    def validate_crop_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Crop name cannot be empty.")

        # Clean spaces: wheat , rice ? wheat,rice
        crops = [c.strip().lower() for c in value.split(",") if c.strip()]
        return ",".join(crops)

class UserDashboardSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.name')

    class Meta:
        model = CustomUser
        fields = ['username', 'cnic', 'section_name', 'role_name', 'created_at']
