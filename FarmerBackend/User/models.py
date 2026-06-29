from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import Group, Permission
from CropsRecomendations.models import CropSeason,CropType
from LinkedValues.models import Districts
import os
from datetime import datetime

class MyUserManager(BaseUserManager):
    def create_user(self, mobile_number, password=None, **extra_fields):
        if not mobile_number:
            raise ValueError(_('The mobile_number field must be set'))

        user = self.model(
            mobile_number=mobile_number,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(
            mobile_number,
            password=password,
            **extra_fields
        )

class Role(models.Model):
    name = models.CharField(max_length=50, blank=False, null=False,unique=True)
    can_send_response = models.BooleanField(default=False)

    def __str__(self):
        return self.name

def profile_picture_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]  # .jpg, .png, etc.

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    user_id = instance.pk or "temp"

    return f"profile_pictures/user_{instance.id}_{timestamp}{ext}"


class CustomUser(AbstractBaseUser, PermissionsMixin):
    STATUS_CHOICES = [
        (True, _('Active')),
        (False, _('Inactive')),
    ]
    STAFF_CHOICES = [
        (True, _('Yes')),
        (False, _('No')),
    ]
    user_creator = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_users',)
    role = models.ForeignKey(Role, on_delete=models.CASCADE,)
    username = models.CharField(max_length=150, null=True, blank=True)  # increase from 30 → 150
    profile_picture = models.ImageField(
    upload_to=profile_picture_upload_path,
    null=True,
    blank=True
)

    section_name = models.CharField(max_length=50,null=True, blank=True)
    mobile_number = models.CharField(max_length=11, null=True, blank=True,unique=True)
    cnic = models.CharField(max_length=13, null=True, blank=True )
    groups = models.ManyToManyField(Group, verbose_name=_('groups'), blank=True, related_name='custom_users')
    user_permissions = models.ManyToManyField(Permission, verbose_name=_('user permissions'), blank=True, related_name='custom_users')
    is_staff = models.BooleanField(default=True)
    is_active = models.BooleanField(choices=STATUS_CHOICES, default=True)
    email = models.EmailField(null=True, blank=True)
    objects = MyUserManager()
    created_at = models.DateTimeField(auto_now_add=True)
    USERNAME_FIELD = 'mobile_number'

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')

    def save(self, *args, **kwargs):
        # Assign default role if none is set
        if not self.role_id:
            role, _ = Role.objects.get_or_create(name="Farmer")
            self.role = role

        # Make username lowercase if it exists
        if self.username:
            self.username = self.username.lower()

        # Save the user object once
        super().save(*args, **kwargs)


    def __str__(self):
        return f"{self.cnic} - {self.username or 'No Name'}"


class Farms(models.Model):
    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=False, blank=False,)
    farm_name = models.CharField(max_length=100,blank=True, null=True,default="farm")
    bbox = bbox = models.TextField(null=False,blank=False)
    crop_season = models.ForeignKey(CropSeason,on_delete=models.SET_NULL,null=True,blank=True)
    crop = models.ForeignKey(CropType,on_delete=models.SET_NULL,null=True,blank=True)
    sowing_date = models.DateField(null=True,blank=True)
    district = models.ForeignKey(Districts,on_delete=models.CASCADE,null=True,blank=True)
    total_acres = models.DecimalField(max_digits=10,decimal_places=2,default=0,null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f'{self.farm_name}'


class UserFollwers(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='user_follwers')
    follower = models.ManyToManyField(CustomUser,  related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)


class UserFollwing(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='user_follwing')
    following = models.ManyToManyField(CustomUser, related_name='following')
    created_at = models.DateTimeField(auto_now_add=True)


class CropDetails(models.Model):
    crop_name = models.TextField(null=False, blank=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.crop_name} -- {self.user}'
