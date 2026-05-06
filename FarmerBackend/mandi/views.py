from datetime import date
from django.utils.dateparse import parse_date
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import MandiDailyData
from .fetcher import fetch_and_save_mandi
from rest_framework.permissions import IsAuthenticated
class MandiDataView(APIView):
    permission_classes = [IsAuthenticated]  
    def filter_city(self, data, city):
        """Utility to filter mandi data by city"""
        if not city or not isinstance(data, dict) or "data" not in data:
            return data

        filtered = [
            c for c in data["data"]
            if c.get("CityName", "").lower() == city.lower()
        ]

        return {
            "status": data.get("status"),
            "date": data.get("date"),
            "total_records": str(len(filtered)),
            "data": filtered
        }

    def format_response(self, source, obj, data):
        """Standard response format"""
        return Response({
            "source": source,
            "date": str(obj.date),
            "total_records": len(data.get("data", [])) if isinstance(data, dict) else 0,
            "data": data
        }, status=status.HTTP_200_OK)

    def get(self, request):

        qdate_str = request.GET.get("date")
        city = request.GET.get("city")

        # ------------------ DATE HANDLING ------------------
        if qdate_str:
            req_date = parse_date(qdate_str)
            if not req_date:
                return Response(
                    {"error": "Invalid date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            req_date = date.today()

        if req_date > date.today():
            return Response(
                {"error": "Future date not allowed"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ------------------ 1) CHECK DATABASE ------------------
        obj = MandiDailyData.objects.filter(date=req_date).first()
        if obj:
            data = self.filter_city(obj.data, city)
            return self.format_response("database", obj, data)

        # ------------------ 2) FETCH FROM API ------------------
        try:
            fetch_and_save_mandi(req_date)
            obj = MandiDailyData.objects.filter(date=req_date).first()

            if obj:
                data = self.filter_city(obj.data, city)
                return self.format_response("api_fetched", obj, data)

        except Exception as e:
            api_error = str(e)
        else:
            api_error = "API returned empty data"

        # ------------------ 3) FALLBACK TO LATEST SAVED ------------------
        last_obj = MandiDailyData.objects.order_by("-date").first()

        if not last_obj:
            return Response(
                {"error": "No mandi data available in database"},
                status=status.HTTP_404_NOT_FOUND
            )

        data = self.filter_city(last_obj.data, city)

        return Response({
            "source": "last_saved_backup",
            "requested_date": str(req_date),
            "error": api_error,
            "date": str(last_obj.date),
            "total_records": len(data.get("data", [])),
            "data": data
        }, status=status.HTTP_200_OK)
