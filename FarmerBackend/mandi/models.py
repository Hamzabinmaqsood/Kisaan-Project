from django.db import models


class MandiDailyData(models.Model):
    date = models.DateField(unique=True, db_index=True)

    # ✅ Full API response saved here
    data = models.JSONField(default=list)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Mandi Data {self.date}"
