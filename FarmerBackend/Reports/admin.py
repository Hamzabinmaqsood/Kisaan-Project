from django.contrib import admin
from .models import Reports


@admin.register(Reports)
class ReportsAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "user",
        "farm",
        "crop_season",
        "crop_type",
        "sowing_date",
        "generated_at",
        "is_successful",
        "report_file_link",
    )

    list_filter = (
        "is_successful",
        "generated_at",
        "crop_season",
        "crop_type",
        "sowing_date",
    )

    search_fields = (
        "user__username",
        "user__mobile_number",
        "farm__farm_name",
        "crop_type__name",
        "crop_season__name",
    )

    readonly_fields = ("generated_at",)

    autocomplete_fields = (
        "user",
        "farm",
    )

    ordering = ("-generated_at",)

    def report_file_link(self, obj):
        if obj.report_file:
            return f"📄 {obj.report_file.url}"
        return "No file"

    report_file_link.short_description = "Report File"