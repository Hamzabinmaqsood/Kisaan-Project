from django.db import models
from CropsRecomendations.models import CropType, CropSeason


class FAQ(models.Model):
    crop_season = models.ForeignKey(
        CropSeason,
        on_delete=models.CASCADE,
        related_name="faqs"
    )
     
    crop = models.ForeignKey(
        CropType,
        on_delete=models.CASCADE,
        related_name="faqs"
    )
   
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.crop.name} - {self.crop_season.name}"


class FAQItem(models.Model):
    faq = models.ForeignKey(
        FAQ,
        on_delete=models.CASCADE,
        related_name="items"
    )
    question = models.TextField()
    answer = models.TextField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.question[:50]