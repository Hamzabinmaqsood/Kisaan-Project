from rest_framework import serializers
from django.db.models import Sum
from .models import MediaMessage, MediaResponse
from User.models import Farms 
from Reports.models import Reports  
from django.db.models import Count, Sum
# -----------------------------
# RESPONSE SERIALIZER
# -----------------------------
class MediaResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaResponse
        fields = ["id", "text", "image", "video", "voice", "created_at"]


# -----------------------------
# MAIN MESSAGE SERIALIZER
# -----------------------------
class MediaMessageSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    responses = MediaResponseSerializer(many=True, read_only=True)
    assigned_user = serializers.SerializerMethodField()
    user_details = serializers.SerializerMethodField()

    class Meta:
        model = MediaMessage
        fields = [
            "id",
            "username",
            "text",
            "image",
            "video",
            "voice",
            "created_at",
            "responses",
            "is_done",
            "assigned_user",
            "user_details",
        ]

    def get_assigned_user(self, obj):
        if hasattr(obj, "assignment") and obj.assignment:
            return {
                "id": obj.assignment.user.id,
                "username": obj.assignment.user.username
            }
        return None

    def get_user_details(self, obj):
        user = obj.user

        farms_qs = Farms.objects.filter(created_by=user)
        reports_qs = Reports.objects.filter(user=user)

        total_reports_user = reports_qs.count()

        # -----------------------------
        # PER FARM REPORT COUNT
        # -----------------------------
        farm_report_map = (
            reports_qs.values("farm_id")
            .order_by()
            .annotate(total_reports=Count("id"))
        )

        farm_report_dict = {
            item["farm_id"]: item["total_reports"]
            for item in farm_report_map
        }

        farms_data = farms_qs.values("id", "bbox", "total_acres")

        total_area = farms_qs.aggregate(
            total=Sum("total_acres")
        )["total"] or 0

        return {
            "id": user.id,
            "username": user.username,
            "cnic": user.cnic,
            "mobile_number": user.mobile_number,

            # ✅ NEW
            "total_reports_generated_by_user": total_reports_user,

            "farms": {
                "total_farms": farms_qs.count(),
                "total_area_acres": total_area,

                "list": [
                    {
                        "farm_id": f["id"],
                        "farm_bbox": f["bbox"],
                        "area_acres": f["total_acres"],

                        # ✅ NEW PER FARM REPORT COUNT
                        "total_reports": farm_report_dict.get(f["id"], 0),
                    }
                    for f in farms_data
                ]
            }
        }
# -----------------------------
# RESPONSE GET SERIALIZER
# -----------------------------
class GET_RESPONSE_MediaResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaResponse
        fields = [
            "id",
            "query",
            "responder",
            "text",
            "image",
            "video",
            "voice",
            "created_at",
        ]