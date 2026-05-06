from django.contrib import admin
from .models import *
# Register your models here.

class AdminSentinal(admin.ModelAdmin):
    list_display = ['farm_id', 'index_type', 'bbox_hash', 'date']


admin.site.register(SentinelIndexCache, AdminSentinal)