from django.db import models
from LinkedValues.models import Districts
# Create your models here.
class CropSeason(models.Model):
    name = models.CharField(max_length=500,null=False,blank=False,unique=True)
    def __str__(self):
        return self.name
    
class CropType(models.Model):
    season = models.ForeignKey(CropSeason,on_delete=models.CASCADE,blank=False,null=False,related_name="crop_types")
    name = models.CharField(max_length=500,null=False,blank=False,unique=True)
    def __str__(self):
        return f'Season: {self.season} , Crop: {self.name}'
    


    


class Recommendation(models.Model):
    season = models.ForeignKey(CropSeason, on_delete=models.CASCADE,null=False,blank=False)
    crop = models.ForeignKey(CropType, on_delete=models.CASCADE,null=False,blank=False)
    def __str__(self):
        return f"{self.season} - {self.crop}"
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "season",
                    "crop",
                ],
                name="unique_recommendation_per_crop_season_range"
            )
        ]
class RecommendationItem(models.Model):
    class IndicesChoices(models.TextChoices):
        NDVI = "NDVI", "NDVI"
        MSAVI = "MSAVI", "MSAVI"
        NDRE = "NDRE", "NDRE"
        RRCL = "ReCL", "ReCL"
        NDMI = "NDMI", "NDMI"
    class CropStages(models.TextChoices):
        PRE_PLANTING_EARLY = "pre_planting_early", "Pre Planting (Early Growth)"
        VEGETATIVE_GROWTH = "vegetative_growth", "Vegetative Growth"
        FLOWERING_REPRODUCTIVE = "flowering_reproductive", "Flowering/Reproductive"
        MATURITY_PRE_HARVEST = "maturity_pre_harvest", "Maturity/Pre-Harvest"

    recommendation = models.ForeignKey(
        Recommendation,
        on_delete=models.CASCADE,
        related_name="items",
        null=False,blank=False
    )

    crop_stage = models.CharField(max_length=50, choices=CropStages.choices,null=False,blank=False)
    indice = models.CharField(max_length=10, choices=IndicesChoices.choices,null=False,blank=False)
    duration_in_days = models.CharField(max_length=500, null=False,blank=False,default="0-30") 
    recommendation_text = models.TextField(null=False,blank=False)

    def __str__(self):
        return f"{self.crop_stage} ({self.duration_in_days}) - {self.indice}: {self.recommendation_text[:50]}..."