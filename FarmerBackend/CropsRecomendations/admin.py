from django.contrib import admin
from .models import (
    CropSeason,
    CropType,
    Recommendation,
    RecommendationItem,
)


# -------------------------
# Inline Admins
# -------------------------

class CropTypeInline(admin.TabularInline):
    model = CropType
    extra = 1
    fields = ("name",)
    show_change_link = True


class RecommendationItemInline(admin.TabularInline):
    model = RecommendationItem
    extra = 1
    fields = ("crop_stage", "indice", "duration_in_days", "recommendation_text")
    show_change_link = True


# -------------------------
# Main Model Admins
# -------------------------

@admin.register(CropSeason)
class CropSeasonAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)
    inlines = [CropTypeInline]


@admin.register(CropType)
class CropTypeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "season")
    search_fields = ("name", "season__name")
    list_filter = ("season",)


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ("id", "season", "crop")
    list_filter = ("season", "crop")
    search_fields = ("season__name", "crop__name")
    inlines = [RecommendationItemInline]
    class Media:
        js = ("admin/js/crop_filter.js",)

# @admin.register(RecommendationItem)
# class RecommendationItemAdmin(admin.ModelAdmin):
#     list_display = ("id", "recommendation", "crop_stage", "indice", "duration_in_days")
#     list_filter = ("crop_stage", "indice")
#     search_fields = (
#         "recommendation__season__name",
#         "recommendation__crop__name",
#         "recommendation_text",
#     )
   