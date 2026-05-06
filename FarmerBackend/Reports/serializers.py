from rest_framework import serializers
from Reports.models import Reports


class ReportsSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)
    farm_name = serializers.CharField(source="farm.farm_name", read_only=True)
    crop_season_name = serializers.CharField(source="crop_season.name", read_only=True)
    crop_type_name = serializers.CharField(source="crop_type.name", read_only=True)

    class Meta:
        model = Reports
        fields = [
            "id",
            "user_name",
            "farm_name",
            "crop_season_name",
            "crop_type_name",
            "sowing_date" ,
            "generated_at",
            "report_file",
            "is_successful",
        ]
class ReportResponseSerializer(serializers.ModelSerializer):
    """Serializer for report API response."""
    
    report_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Reports
        fields = ['id', 'report_url', 'generated_at']
        read_only_fields = ['id', 'generated_at']
    
    def get_report_url(self, obj: Reports) -> str:
        """
        Get the absolute URL for the report file.
        
        Args:
            obj: Reports instance
            
        Returns:
            str: Absolute URL to the report PDF
        """
        request = self.context.get('request')
        
        if obj.report_file and hasattr(obj.report_file, 'url'):
            if request is not None:
                return request.build_absolute_uri(obj.report_file.url)
            return obj.report_file.url
        
        return None