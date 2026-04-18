"""
Proon AI — Django Models

Defines the database schema for:
- TFLite model registry  (OTA model delivery to Flutter clients)
- Plant categories and detection labels (from labels.txt)
- Rule-based detection results (Lite mode)
- Chat sessions and messages
- Scan history
"""
from django.db import models
from django.conf import settings
import uuid


# ---------------------------------------------------------------------------
# TFLite Model Registry — OTA Model Delivery
# ---------------------------------------------------------------------------

def _tflite_upload_path(instance, filename):
    """Store versioned model files under media/models/<version>/."""
    return f"models/{instance.version}/{filename}"


class TFLiteModel(models.Model):
    """
    Registry of TFLite model releases.

    How it works:
      1. Admin uploads a new .tflite file and labels.txt via Django Admin.
      2. Admin sets is_active=True (previous active record is deactivated automatically).
      3. Flutter app calls GET /api/model/version/ on startup.
      4. If the returned version differs from the cached version on-device,
         the app downloads model_file_url and labels_file_url, caches them locally,
         and uses the new model for all future Lite-mode scans — no app update needed.

    Only ONE record should be active at any time. The admin action in admin.py
    enforces this automatically.
    """
    version = models.CharField(
        max_length=30,
        unique=True,
        help_text='Semantic version string, e.g. "v1.0.0". Must be unique across all releases.',
    )
    model_file = models.FileField(
        upload_to=_tflite_upload_path,
        help_text='Upload the .tflite model file here. It will be served at a stable URL.',
    )
    labels_file = models.FileField(
        upload_to=_tflite_upload_path,
        help_text='Upload the labels.txt file that pairs with this model.',
    )
    is_active = models.BooleanField(
        default=False,
        help_text=(
            'Mark this release as the one served to Flutter clients. '
            'Only ONE release should be active at a time. '
            'Activating this record deactivates all others automatically.'
        ),
    )
    changelog = models.TextField(
        blank=True,
        help_text='Optional release notes / description of what changed in this model version.',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'TFLite Model Release'
        verbose_name_plural = 'TFLite Model Releases'

    def __str__(self):
        status = '✓ ACTIVE' if self.is_active else 'archived'
        return f'{self.version} [{status}]'

    def save(self, *args, **kwargs):
        """
        When this release is activated, deactivate all other releases.
        Guarantees only one active release exists at any time.
        """
        if self.is_active:
            TFLiteModel.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Plant Catalogue
# ---------------------------------------------------------------------------

class PlantCategory(models.Model):
    """
    Represents a plant type (e.g. Apple, Sprouts, Plum).
    Maps to the model cards shown on the Models screen.
    """
    name = models.CharField(max_length=100)
    scientific_name = models.CharField(max_length=200, blank=True)
    icon_url = models.URLField(blank=True)
    description = models.TextField(blank=True)
    accuracy = models.FloatField(default=98.9, help_text='Model accuracy percent')
    latency_ms = models.IntegerField(default=15, help_text='Inference latency in ms')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Plant Categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class DetectionLabel(models.Model):
    """
    Maps a TFLite model output label (from labels.txt) to a PlantCategory.
    E.g. label_key='Sprouts' → PlantCategory(name='Sprouts')
    """
    label_key = models.CharField(
        max_length=100, unique=True,
        help_text='Must match exactly what labels.txt contains'
    )
    plant_category = models.ForeignKey(
        PlantCategory, on_delete=models.CASCADE, related_name='labels'
    )

    def __str__(self):
        return f'{self.label_key} → {self.plant_category.name}'


class DetectionRule(models.Model):
    """
    Rule-based detection result for LITE (LOCAL) mode.
    When TFLite returns a label, we look up its DetectionRule to display
    ripeness info, tips, and recommendations — without calling Gemini.
    """
    STATUS_CLASSIFIED = 'Classified'
    STATUS_UNCLASSIFIED = 'Unclassified'
    STATUS_CHOICES = [
        (STATUS_CLASSIFIED, 'Classified'),
        (STATUS_UNCLASSIFIED, 'Unclassified'),
    ]

    label = models.OneToOneField(
        DetectionLabel, on_delete=models.CASCADE, related_name='rule'
    )
    ripeness_score = models.IntegerField(
        default=0,
        help_text='0–100 ripeness/readiness percent shown on the result card'
    )
    ripeness_label = models.CharField(
        max_length=50, default='Unknown',
        help_text='e.g. Low / Medium / High / Very High'
    )
    peak_window = models.CharField(
        max_length=200, blank=True,
        help_text='e.g. "Harvest within 3–5 days"'
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_CLASSIFIED
    )
    # Stored as JSON list of strings
    quick_tips = models.JSONField(
        default=list,
        help_text='Short actionable tips shown as bullet list on result card'
    )
    detection_detail = models.TextField(
        help_text='Detailed paragraph shown under Detection Detail section'
    )
    # Stored as JSON list of strings
    recommendations = models.JSONField(
        default=list,
        help_text='More Recommendations section on result card'
    )
    reference_image_url = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Rule for {self.label.label_key}'


class ScanHistory(models.Model):
    """
    Stores each scan the user performs (both Lite and Pro).
    Needed for the History tab in the app.
    """
    MODE_LITE = 'lite'
    MODE_PRO = 'pro'
    MODE_CHOICES = [
        (MODE_LITE, 'Lite (Local)'),
        (MODE_PRO, 'Pro (Global)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='scans',
        null=True, blank=True  # allow anonymous for now
    )
    mode = models.CharField(max_length=10, choices=MODE_CHOICES)
    detected_label = models.CharField(max_length=100)
    confidence = models.FloatField(default=0.0)
    ripeness_score = models.IntegerField(default=0)
    ripeness_label = models.CharField(max_length=50, blank=True)
    peak_window = models.CharField(max_length=200, blank=True)
    detection_detail = models.TextField(blank=True)
    quick_tips = models.JSONField(default=list)
    recommendations = models.JSONField(default=list)
    # For Pro mode: store the image temporarily (or just URL if using cloud storage)
    image_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Scan History'

    def __str__(self):
        return f'[{self.mode.upper()}] {self.detected_label} @ {self.created_at:%Y-%m-%d %H:%M}'


class ChatSession(models.Model):
    """
    A conversation session between user and Proon AI chatbot.
    Each ScanHistory can have one ChatSession linked to it.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_sessions',
        null=True, blank=True
    )
    scan = models.OneToOneField(
        ScanHistory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='chat_session'
    )
    mode = models.CharField(max_length=10, choices=ScanHistory.MODE_CHOICES)
    # Context snapshot injected into every Gemini prompt for this session
    context_label = models.CharField(max_length=100, blank=True)
    context_data = models.JSONField(
        default=dict,
        help_text='Serialized detection result injected as AI context'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Session {self.id} [{self.mode}] — {self.context_label}'


class ChatMessage(models.Model):
    """
    Individual messages within a ChatSession.
    """
    ROLE_USER = 'user'
    ROLE_ASSISTANT = 'assistant'
    ROLE_CHOICES = [
        (ROLE_USER, 'User'),
        (ROLE_ASSISTANT, 'Assistant'),
    ]

    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name='messages'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f'[{self.role}] {self.content[:60]}'
