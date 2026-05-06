import uuid
import os
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


# -----------------------------
# FILE SIZE VALIDATOR (20MB)
# -----------------------------
def validate_file_size_20mb(file):
    max_size = 20 * 1024 * 1024  # 20MB
    if file.size > max_size:
        raise ValidationError("File size must be <= 20MB")


# -----------------------------
# TEMP UPLOAD PATH (we will rename later)
# -----------------------------
def temp_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"querry/temp/{uuid.uuid4()}{ext}"


# -----------------------------
# QUERY MODEL
# -----------------------------
class MediaMessage(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="queries"
    )

    text = models.TextField(blank=True, null=True)

    image = models.ImageField(upload_to=temp_upload_path, blank=True, null=True, validators=[validate_file_size_20mb])
    video = models.FileField(upload_to=temp_upload_path, blank=True, null=True, validators=[validate_file_size_20mb])
    voice = models.FileField(upload_to=temp_upload_path, blank=True, null=True, validators=[validate_file_size_20mb])
    is_done = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"QUERY {self.id} - {self.user}"



# -----------------------------
# RESPONSE MODEL
# -----------------------------
class MediaResponse(models.Model):
    query = models.ForeignKey(
        MediaMessage,
        on_delete=models.CASCADE,
        related_name="responses"
    )

    responder = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="responses_sent"
    )

    text = models.TextField(blank=True, null=True)

    image = models.ImageField(upload_to=temp_upload_path, blank=True, null=True, validators=[validate_file_size_20mb])
    video = models.FileField(upload_to=temp_upload_path, blank=True, null=True, validators=[validate_file_size_20mb])
    voice = models.FileField(upload_to=temp_upload_path, blank=True, null=True, validators=[validate_file_size_20mb])

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"RESPONSE {self.id} for QUERY {self.query.id}"


class AssignedQuery(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assigned_queries"
    )

    query = models.OneToOneField(   # ✅ prevents duplicate assignment
        MediaMessage,
        on_delete=models.CASCADE,
        related_name="assignment"
    )

    assigned_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.query} → {self.user}"
