from django.db import models
from django.utils import timezone
from User.models import CustomUser, Farms
from CropsRecomendations.models import CropSeason, CropType
import os


def report_upload_path(instance, filename):
    now = timezone.now()
    readable_time = now.strftime("%Y%m%d_%I%M%p").lower()
    user_mobile = getattr(instance.user, "mobile_number", "user")
    farm_name = instance.farm.farm_name.replace(" ", "_")
    new_filename = f"{farm_name}_{user_mobile}_{readable_time}.pdf"
    return os.path.join("reports", new_filename)


class Reports(models.Model):
    class Status(models.TextChoices):
        STARTED = "STARTED", "Started"
        FAILED  = "FAILED",  "Failed"
        DONE    = "DONE",    "Done"

    class Report_TYPE(models.TextChoices):
        FARMER = "FARMER", "farmer"
        AGRO  = "AGRO",  "agro"
        

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="user_reports"
    )
    farm = models.ForeignKey(
        Farms,
        on_delete=models.CASCADE,
        related_name="user_report_farms"
    )
    crop_season = models.ForeignKey(
        CropSeason,
        on_delete=models.CASCADE,
        related_name="report_crop_season"
    )
    crop_type = models.ForeignKey(
        CropType,
        on_delete=models.CASCADE,
        related_name="report_crop_type"
    )
    sowing_date    = models.DateField()
    generated_at   = models.DateTimeField(auto_now_add=True)
    report_file    = models.FileField(upload_to=report_upload_path, null=True, blank=True)
    status         = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.STARTED,
    )
    report_type = models.CharField(
        max_length=50,
        choices=Report_TYPE.choices,
        default=Report_TYPE.FARMER,
    )
    is_successful  = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.farm.farm_name} - {self.user}"

    # ── convenience helpers ────────────────────────────────────────────

    def mark_done(self) -> None:
        self.status = self.Status.DONE
        self.is_successful = True
        self.save(update_fields=["status", "is_successful"])

    def mark_failed(self) -> None:
        self.status = self.Status.FAILED
        self.is_successful = False
        self.save(update_fields=["status", "is_successful"])