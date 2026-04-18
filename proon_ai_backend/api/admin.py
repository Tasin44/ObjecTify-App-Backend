from django.contrib import admin
from django.utils.html import format_html
from .models import TFLiteModel, PlantCategory, DetectionLabel, DetectionRule, ScanHistory, ChatSession, ChatMessage


# ---------------------------------------------------------------------------
# TFLite Model Registry
# ---------------------------------------------------------------------------

@admin.action(description='Activate selected release (deactivates all others)')
def activate_model_release(modeladmin, request, queryset):
    """
    Admin bulk action: activates the selected TFLiteModel release.
    Because TFLiteModel.save() handles mutual exclusivity, we just need
    to call save() on the selected record with is_active=True.
    Only one record should be selected; warns if more than one is chosen.
    """
    if queryset.count() != 1:
        modeladmin.message_user(
            request,
            'Please select exactly ONE release to activate.',
            level='error',
        )
        return
    release = queryset.first()
    release.is_active = True
    release.save()  # .save() deactivates all others automatically
    modeladmin.message_user(
        request,
        f'Release {release.version} is now active. All other releases have been deactivated.',
    )


@admin.register(TFLiteModel)
class TFLiteModelAdmin(admin.ModelAdmin):
    list_display = ['version', 'status_badge', 'uploaded_at', 'updated_at']
    list_filter = ['is_active']
    readonly_fields = ['uploaded_at', 'updated_at']
    actions = [activate_model_release]
    ordering = ['-uploaded_at']

    fieldsets = [
        ('Release Info', {
            'fields': ['version', 'is_active', 'changelog'],
            'description': (
                '<strong>Workflow:</strong> '
                '1. Upload the .tflite and labels.txt files below. '
                '2. Set a unique version string (e.g. v1.2.0). '
                '3. Tick “Is active” or use the “Activate” action from the list view. '
                'Flutter clients will download the new model on their next app launch.'
            ),
        }),
        ('Files', {
            'fields': ['model_file', 'labels_file'],
        }),
        ('Timestamps', {
            'fields': ['uploaded_at', 'updated_at'],
            'classes': ['collapse'],
        }),
    ]

    @admin.display(description='Status', boolean=False)
    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: #16a34a; font-weight: bold">✓ ACTIVE</span>')
        return format_html('<span style="color: #6b7280">archived</span>')



@admin.register(PlantCategory)
class PlantCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'scientific_name', 'accuracy', 'latency_ms']
    search_fields = ['name', 'scientific_name']


@admin.register(DetectionLabel)
class DetectionLabelAdmin(admin.ModelAdmin):
    list_display = ['label_key', 'plant_category']
    list_select_related = ['plant_category']


@admin.register(DetectionRule)
class DetectionRuleAdmin(admin.ModelAdmin):
    list_display = ['label', 'ripeness_score', 'ripeness_label', 'peak_window', 'status']
    list_select_related = ['label']
    fieldsets = [
        ('Classification', {
            'fields': ['label', 'status'],
        }),
        ('Ripeness', {
            'fields': ['ripeness_score', 'ripeness_label', 'peak_window'],
        }),
        ('Content', {
            'fields': ['quick_tips', 'detection_detail', 'recommendations', 'reference_image_url'],
        }),
    ]


@admin.register(ScanHistory)
class ScanHistoryAdmin(admin.ModelAdmin):
    list_display = ['detected_label', 'mode', 'confidence', 'ripeness_label', 'created_at']
    list_filter = ['mode', 'created_at']
    search_fields = ['detected_label']
    readonly_fields = ['id', 'created_at']


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'mode', 'context_label', 'created_at']
    list_filter = ['mode']
    readonly_fields = ['id', 'created_at']


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['session', 'role', 'content_preview', 'timestamp']
    list_filter = ['role']

    def content_preview(self, obj):
        return obj.content[:60]
    content_preview.short_description = 'Content'
