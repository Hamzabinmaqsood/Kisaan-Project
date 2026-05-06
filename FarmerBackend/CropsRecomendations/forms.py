from django import forms
from django.core.exceptions import ValidationError
from .models import Recommendation, CropType


class RecommendationAdminForm(forms.ModelForm):
    class Meta:
        model = Recommendation
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["crop"].queryset = CropType.objects.none()

        if self.instance and self.instance.pk:
            self.fields["crop"].queryset = CropType.objects.filter(
                season=self.instance.season
            )

        elif "season" in self.data:
            try:
                season_id = int(self.data.get("season"))
                self.fields["crop"].queryset = CropType.objects.filter(
                    season_id=season_id
                )
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned = super().clean()

        season = cleaned.get("season")
        crop = cleaned.get("crop")
        sow = cleaned.get("sowing_month")
        harvest = cleaned.get("harvesting_month")

        if season and crop and crop.season != season:
            raise ValidationError("Selected crop does not belong to selected season.")

        if sow and harvest and sow >= harvest:
            raise ValidationError("Sowing month must be before harvesting month.")

        return cleaned