from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserSubscription


@receiver(post_save, sender=get_user_model())
def create_default_subscription(sender, instance, created, **kwargs):
    if created:
        UserSubscription.objects.get_or_create(user=instance)
