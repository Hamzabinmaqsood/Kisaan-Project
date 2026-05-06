from django.contrib import admin
from .models import *


# -----------------------------
# INLINE RESPONSES INSIDE QUERY
# -----------------------------
class MediaResponseInline(admin.TabularInline):
    model = MediaResponse
    extra = 0
    readonly_fields = ("id", "created_at")
    fields = ("id", "responder", "text", "image", "video", "voice", "created_at")


# -----------------------------
# QUERY ADMIN
# -----------------------------
@admin.register(MediaMessage)
class MediaMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "text_preview", "created_at")
    list_filter = ("created_at", "user")
    search_fields = ("id", "user__username", "user__email", "text")
    readonly_fields = ("id", "created_at")

    inlines = [MediaResponseInline]

    def text_preview(self, obj):
        if obj.text:
            return obj.text[:40]
        return "-"
    text_preview.short_description = "Text Preview"


# -----------------------------
# RESPONSE ADMIN
# -----------------------------
@admin.register(MediaResponse)
class MediaResponseAdmin(admin.ModelAdmin):
    list_display = ("id", "query", "responder", "text_preview", "created_at")
    list_filter = ("created_at", "responder")
    search_fields = ("id", "query__id", "responder__username", "responder__email", "text")
    readonly_fields = ("id", "created_at")

    def text_preview(self, obj):
        if obj.text:
            return obj.text[:40]
        return "-"
    text_preview.short_description = "Text Preview"
admin.site.register(AssignedQuery)