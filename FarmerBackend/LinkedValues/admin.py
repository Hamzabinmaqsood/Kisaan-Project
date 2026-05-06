from django.contrib import admin
from .models import Districts

@admin.register(Districts)
class DistrictsAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)
    ordering = ('name',)