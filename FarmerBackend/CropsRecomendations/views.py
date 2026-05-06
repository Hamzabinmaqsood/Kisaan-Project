from django.http import JsonResponse
from .models import *

def get_crops_by_season(request):
    season_id = request.GET.get("season_id")

    crops = CropType.objects.filter(season_id=season_id).values("id", "name")

    return JsonResponse(list(crops), safe=False)



def crops_grouped_by_season(request):
    data = []
    seasons = CropSeason.objects.prefetch_related("crop_types").all()
    for season in seasons:
        data.append({
            "season_id": season.id,
            "season_name": season.name,
            "crops": [
                {
                    "id": crop.id,
                    "name": crop.name
                }
                for crop in season.crop_types.all()
            ]
        })

    return JsonResponse(data, safe=False)