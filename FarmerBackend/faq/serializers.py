from rest_framework import serializers
from .models import FAQ, FAQItem
from CropsRecomendations.models import CropType, CropSeason


class FAQItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQItem
        fields = ["id", "question", "answer", "is_active"]


class FAQSerializer(serializers.ModelSerializer):
    crop_name = serializers.CharField(source="crop.name", read_only=True)
    season_name = serializers.CharField(source="crop_season.name", read_only=True)

    # only active items
    items = serializers.SerializerMethodField()

    class Meta:
        model = FAQ
        fields = [
            "id",
            "crop",
            "crop_name",
            "crop_season",
            "season_name",
            "created_at",
            "items",
        ]

    def get_items(self, obj):
        active_items = obj.items.filter(is_active=True)
        return FAQItemSerializer(active_items, many=True).data


class CropSerializer(serializers.ModelSerializer):
    season_name = serializers.CharField(source="season.name", read_only=True)

    class Meta:
        model = CropType
        fields = ["id", "name", "season_name"]