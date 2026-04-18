# models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid
import random
import string

class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=False)
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)
    referral_code = models.CharField(max_length=20, blank=True, null=True)
    verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Add these two lines
    groups = models.ManyToManyField(
        'auth.Group', related_name='authapp_user_set', blank=True
    )
    class Meta:
        indexes = [
            models.Index(fields=['email', 'verified']),
            models.Index(fields=['verified']),
        ]

    def __str__(self):
        return self.email

class OTP(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    otp_code = models.CharField(max_length=6)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()#self.expires_at just means the expiry time stored in that OTP object in signup serializer
    
    class Meta:
        indexes = [
            models.Index(fields=['email', 'is_used']),
        ]
    
    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at
    
    def __str__(self):
        return f"{self.email} - {self.otp_code}"


class Personalization(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='personalization')
    surface_area = models.CharField(max_length=100)
    fruit_tress = models.IntegerField()
    fruit_tree_types = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} personalization"
    
