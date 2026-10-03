from django.apps import AppConfig
from django.db.models.signals import post_save


def _ensure_profile(sender, instance, created, **kwargs):
    if created:
        from core.models import Profile

        # Superusers created from the CLI chose their own password, so don't force a change.
        Profile.objects.get_or_create(user=instance, defaults={"must_change_password": not instance.is_superuser})


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        from django.contrib.auth import get_user_model

        post_save.connect(_ensure_profile, sender=get_user_model(), dispatch_uid="ll_ensure_profile")
