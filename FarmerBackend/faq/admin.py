from django.contrib import admin
from .models import FAQ, FAQItem


class FAQItemInline(admin.TabularInline):
    model = FAQItem
    extra = 1


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("crop_name", "season_name", "created_at")
    inlines = [FAQItemInline]
    search_fields = ("crop__name", "crop_season__name")
    list_filter = ("crop", "crop_season")
    ordering = ("-created_at",)

    def crop_name(self, obj):
        return obj.crop.name
    crop_name.short_description = "Crop"

    def season_name(self, obj):
        return obj.crop_season.name
    season_name.short_description = "Season"
    class Media:
        js = ("admin/js/crop_filter.js",)