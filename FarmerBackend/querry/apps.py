from django.apps import AppConfig


class QuerryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "querry"

    def ready(self):
        import querry.signals
