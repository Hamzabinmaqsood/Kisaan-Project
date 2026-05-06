import os
import shutil
from django.conf import settings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import MediaMessage, MediaResponse


def get_username(user):
    return getattr(user, "username", None) or getattr(user, "email", "unknown_user")


def get_user_folder(user):
    return f"{get_username(user)}_{user.id}"


def move_file(file_field, new_relative_path):
    if not file_field:
        return None

    old_path = file_field.path
    new_path = os.path.join(settings.MEDIA_ROOT, new_relative_path)

    os.makedirs(os.path.dirname(new_path), exist_ok=True)

    if os.path.isfile(old_path):
        shutil.move(old_path, new_path)

    return new_relative_path


# ======================================================
# AFTER SAVE QUERY => MOVE FILES TO: querry/ali_2/query_7.*
# ======================================================
@receiver(post_save, sender=MediaMessage)
def rename_query_files(sender, instance, created, **kwargs):
    if not created:
        return

    folder = get_user_folder(instance.user)

    for field_name in ["image", "video", "voice"]:
        f = getattr(instance, field_name)
        if f:
            ext = os.path.splitext(f.name)[1].lower()
            new_rel = f"querry/{folder}/query_{instance.id}{ext}"
            moved_rel = move_file(f, new_rel)
            setattr(instance, field_name, moved_rel)

    instance.save(update_fields=["image", "video", "voice"])


# ======================================================
# AFTER SAVE RESPONSE => MOVE FILES TO: querry/ali_2/response_7.*
# IMPORTANT: response name uses QUERY ID
# ======================================================
@receiver(post_save, sender=MediaResponse)
def rename_response_files(sender, instance, created, **kwargs):
    if not created:
        return

    folder = get_user_folder(instance.query.user)

    # count responses for this query
    resp_no = MediaResponse.objects.filter(query=instance.query).count()

    for field_name in ["image", "video", "voice"]:
        f = getattr(instance, field_name)
        if f:
            ext = os.path.splitext(f.name)[1].lower()

            # ✅ response_10_1.mp3, response_10_2.mp3 ...
            new_rel = f"querry/{folder}/response_{instance.query.id}_{resp_no}{ext}"
            moved_rel = move_file(f, new_rel)
            setattr(instance, field_name, moved_rel)

    instance.save(update_fields=["image", "video", "voice"])


# ======================================================
# DELETE RESPONSE FILES
# ======================================================
@receiver(post_delete, sender=MediaResponse)
def delete_response_files(sender, instance, **kwargs):
    for field_name in ["image", "video", "voice"]:
        f = getattr(instance, field_name)
        if f and hasattr(f, "path"):
            try:
                if os.path.isfile(f.path):
                    os.remove(f.path)
            except:
                pass


# ======================================================
# DELETE QUERY FILES
# ======================================================
@receiver(post_delete, sender=MediaMessage)
def delete_query_files(sender, instance, **kwargs):
    for field_name in ["image", "video", "voice"]:
        f = getattr(instance, field_name)
        if f and hasattr(f, "path"):
            try:
                if os.path.isfile(f.path):
                    os.remove(f.path)
            except:
                pass


# ======================================================
# IF USER HAS NO QUERIES LEFT => DELETE USER FOLDER
# ======================================================
@receiver(post_delete, sender=MediaMessage)
def delete_user_folder_if_empty(sender, instance, **kwargs):
    user = instance.user

    if not MediaMessage.objects.filter(user=user).exists():
        folder = get_user_folder(user)
        folder_path = os.path.join(settings.MEDIA_ROOT, "querry", folder)

        if os.path.isdir(folder_path):
            shutil.rmtree(folder_path, ignore_errors=True)