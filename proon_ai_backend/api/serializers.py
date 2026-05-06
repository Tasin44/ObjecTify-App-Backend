"""
Proon AI — DRF Serializers
"""
from rest_framework import serializers
from .models import TFLiteModel, PlantCategory, DetectionLabel, DetectionRule, ScanHistory, ChatSession, ChatMessage


class TFLiteModelSerializer(serializers.ModelSerializer):
    """
    Returned by GET /api/model/version/.

    model_file_url and labels_file_url are absolute URLs so the Flutter app
    can download the files directly with a single GET request — no additional
    path construction needed on the client side.
    """
    model_file_url = serializers.SerializerMethodField()
    labels_file_url = serializers.SerializerMethodField()

    class Meta:
        model = TFLiteModel
        fields = ['version', 'model_file_url', 'labels_file_url', 'changelog', 'uploaded_at']

    def get_model_file_url(self, obj):
        request = self.context.get('request')
        if obj.model_file and request:
            return request.build_absolute_uri(obj.model_file.url)
        return None

    def get_labels_file_url(self, obj):
        request = self.context.get('request')
        if obj.labels_file and request:
            return request.build_absolute_uri(obj.labels_file.url)
        return None


class PlantCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantCategory
        fields = ['id', 'name', 'scientific_name', 'icon_url', 'description', 'accuracy', 'latency_ms']


class DetectionRuleSerializer(serializers.ModelSerializer):
    label_key = serializers.CharField(source='label.label_key', read_only=True)
    plant_name = serializers.SerializerMethodField()
    scientific_name = serializers.SerializerMethodField()
    reference_image = serializers.SerializerMethodField()

    class Meta:
        model = DetectionRule
        fields = [
            'label_key', 'plant_name', 'scientific_name',
            'ripeness_score', 'ripeness_label', 'peak_window', 'status',
            'quick_tips', 'detection_detail', 'recommendations',
            'reference_image',
        ]

    def get_reference_image(self, obj):
        return obj.reference_image_url or None

    def get_plant_name(self, obj):
        if obj.label and obj.label.plant_category:
            return obj.label.plant_category.name
        return None

    def get_scientific_name(self, obj):
        if obj.label and obj.label.plant_category:
            return obj.label.plant_category.scientific_name
        return None


class ScanHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ScanHistory
        fields = [
            'id', 'mode', 'detected_label', 'confidence',
            'ripeness_score', 'ripeness_label', 'peak_window',
            'detection_detail', 'quick_tips', 'recommendations',
            'image_url', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'role', 'content', 'timestamp']


class ChatSessionSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = ChatSession
        fields = ['id', 'mode', 'context_label', 'context_data', 'created_at', 'messages']


# ---------------------------------------------------------------------------
# Request / Input Serializers
# ---------------------------------------------------------------------------

class LiteDetectRequestSerializer(serializers.Serializer):
    """Input for POST /api/detect/lite/"""
    label = serializers.CharField(max_length=100)
    confidence = serializers.FloatField(min_value=0.0, max_value=1.0)


class ProDetectRequestSerializer(serializers.Serializer):
    """Input for POST /api/detect/pro/"""
    image_base64 = serializers.CharField(help_text='Base64-encoded image bytes')
    mime_type = serializers.ChoiceField(
        choices=['image/jpeg', 'image/png', 'image/webp'],
        default='image/jpeg'
    )


class ChatRequestSerializer(serializers.Serializer):
    """Input for POST /api/chat/"""
    session_id = serializers.UUIDField(required=False, allow_null=True)
    scan_id = serializers.UUIDField(required=False, allow_null=True)
    message = serializers.CharField(max_length=2000)
    mode = serializers.ChoiceField(choices=['lite', 'pro'])
    context = serializers.DictField(required=False, default=dict)
