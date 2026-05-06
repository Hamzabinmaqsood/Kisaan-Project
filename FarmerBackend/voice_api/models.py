from django.db import models

class SentinelIndexCache(models.Model):
    farm_id = models.ForeignKey('User.Farms', on_delete=models.CASCADE,null=False, blank=False)
    index_type = models.CharField(max_length=10)
    bbox_hash = models.CharField(max_length=64)
    bbox = models.JSONField()
    date = models.DateField()

    image_base64 = models.TextField()
    statistics = models.JSONField()

    audio_file = models.CharField(max_length=255, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("index_type", "bbox_hash", "date","farm_id")
