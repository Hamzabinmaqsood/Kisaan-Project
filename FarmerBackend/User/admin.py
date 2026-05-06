from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import *
from .forms import CustomUserCreationForm, CustomUserChangeForm
from django.conf import settings

class CustomUserAdmin(BaseUserAdmin):
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm

    list_display = ("id",'cnic', 'username', 'role', 'is_staff', 'is_active', "section_name", "user_creator")
    list_filter = ('is_staff', 'is_active', 'role', "section_name")

    fieldsets = (
        (None, {'fields': ('mobile_number', 'password')}),
        ('Personal Info', {'fields': ('username', 'email', 'cnic', 'role', "section_name")}),
        ('Permissions', {'fields': ('is_staff', 'is_active', 'is_superuser', 'groups', 'user_permissions')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('mobile_number', 'password1', 'password2'),
        }),
    )

    search_fields = ('cnic', "username","mobile_number")
    ordering = ('id',)
    filter_horizontal = ('groups', 'user_permissions',)

    def save_model(self, request, obj, form, change):
        # Only set user_creator when creating a new user
        if not change and not obj.user_creator:
            obj.user_creator = request.user
        super().save_model(request, obj, form, change)



class AdminFarms(admin.ModelAdmin):
    autocomplete_fields  = ['created_by']
    list_display = ('id','created_by__username','farm_name', 'bbox', 'created_at' ,"total_acres")
    search_fields = ('farm_name',"created_by__username","crop__name","crop_season__name")
    list_filter = ('created_at',"crop_season","crop")

    class Media:
        js = ['admin/js/custom_button_js.js',"admin/js/crop_filter.js"] 

class AdminRole(admin.ModelAdmin):
    list_display = ("id",'name',"can_send_response",)
    search_fields = ("id",'name',)
admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Farms, AdminFarms)
admin.site.register(Role, AdminRole)
admin.site.register(CropDetails)
