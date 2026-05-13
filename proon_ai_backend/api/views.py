"""
Proon AI — API Views

Endpoints:
  POST /api/detect/lite/       — TFLite result → rule-based DB lookup
  POST /api/detect/pro/        — Image → Gemini Vision → structured result
  POST /api/chat/              — Chatbot (both modes, Gemini-powered)
  GET  /api/models/            — List available plant models
  GET  /api/model/version/     — Active TFLite release info (OTA model delivery)
  GET  /api/history/           — User's scan history
  GET  /api/history/<scan_id>/ — Single scan detail
"""
import base64
import logging
import uuid
from io import BytesIO

from django.shortcuts import get_object_or_404
from django.db import IntegrityError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from PIL import Image, ImageOps, UnidentifiedImageError

from .models import (
    TFLiteModel,
    DetectionLabel,
    DetectionRule,
    PlantCategory,
    ScanHistory,
    ChatSession,
    ChatMessage,
)
from .serializers import (
    TFLiteModelSerializer,
    LiteDetectRequestSerializer,
    ProDetectRequestSerializer,
    ChatRequestSerializer,
    DetectionRuleSerializer,
    ScanHistorySerializer,
    PlantCategorySerializer,
    ChatMessageSerializer,
    ProDetectUrlRequestSerializer
)
from . import gemini_service

logger = logging.getLogger(__name__)


def _resize_image_bytes(image_bytes, mime_type, max_side=1280):
    """Downscale and recompress uploaded images for safer upstream processing."""
    format_map = {
        'image/jpeg': 'JPEG',
        'image/png': 'PNG',
        'image/webp': 'WEBP',
    }
    mime_by_format = {
        'JPEG': 'image/jpeg',
        'PNG': 'image/png',
        'WEBP': 'image/webp',
    }

    try:
        with Image.open(BytesIO(image_bytes)) as img:
            img = ImageOps.exif_transpose(img)
            out_format = format_map.get(mime_type, img.format or 'JPEG')
            out_mime_type = mime_by_format.get(out_format, 'image/jpeg')

            width, height = img.size
            max_dim = max(width, height)
            if max_dim > max_side:
                scale = max_side / float(max_dim)
                new_size = (int(width * scale), int(height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            save_kwargs = {}
            if out_format == 'JPEG':
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                save_kwargs.update({'quality': 85, 'optimize': True, 'progressive': True})
            elif out_format == 'PNG':
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGBA')
                save_kwargs.update({'optimize': True, 'compress_level': 9})
            elif out_format == 'WEBP':
                save_kwargs.update({'quality': 80, 'method': 6})

            output = BytesIO()
            img.save(output, format=out_format, **save_kwargs)
            return output.getvalue(), out_mime_type
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError('Invalid image data') from exc


def _extract_detected_labels(detection_detail: str) -> list:
    if not detection_detail:
        return []
    text = detection_detail.strip()
    if not text.lower().startswith("detected objects:"):
        return []
    detected_list = text.split(":", 1)[1]
    return [
        item.strip(" .")
        for item in detected_list.split(",")
        if item.strip(" .")
    ]


def _build_initial_prompt_for_scan(scan, mode: str, model_name: str = "selected model") -> str:
    if mode == ScanHistory.MODE_LITE:
        label_obj = DetectionLabel.objects.select_related('plant_category').filter(
            label_key__iexact=scan.detected_label
        ).first()
        if label_obj and label_obj.plant_category:
            model_name = label_obj.plant_category.name

    labels = _extract_detected_labels(scan.detection_detail)
    if not labels and scan.detected_label:
        labels = [scan.detected_label]

    if labels:
        labels_text = ", ".join(f"{label}" for label in labels)
        return (
            f"I am pruning this {model_name} and I've identified {labels_text}. "
            "How should I proceed next?"
        )

    return (
        f"I am pruning this {model_name} and I've not identified any labels. "
        "How should I proceed next?"
    )


# ---------------------------------------------------------------------------
# LITE MODE — Rule-Based Detection
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([AllowAny])
def detect_lite(request):
    """
    POST /api/detect/lite/

    Receives TFLite classification output from the Flutter app.
    Looks up the rule-based DetectionRule for that label in the database.
    Returns the full result card data (ripeness, tips, recommendations, etc.)

    Request body:
        {
            "label": "Sprouts",
            "confidence": 0.94
        }

    Response:
        Full DetectionRule as JSON + saved ScanHistory ID
    """
    logger.info('detect_lite request data: %s', request.data)
    serializer = LiteDetectRequestSerializer(data=request.data)
    if not serializer.is_valid():
        logger.warning('detect_lite validation errors: %s', serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    label_key = serializer.validated_data['label']
    confidence = serializer.validated_data['confidence']
    logger.info('detect_lite parsed label=%s confidence=%s', label_key, confidence)

    # Look up the detection label
    try:
        detection_label = DetectionLabel.objects.select_related(
            'plant_category', 'rule'
        ).get(label_key__iexact=label_key)
    except DetectionLabel.DoesNotExist:
        return Response(
            {
                'error': f'No detection rule found for label: "{label_key}"',
                'hint': 'Admin needs to add this label in the database.',
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # Get the rule
    try:
        rule = detection_label.rule
    except DetectionRule.DoesNotExist:
        return Response(
            {'error': f'Detection rule exists for label but has no result data configured.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Save to history
    user = request.user if request.user.is_authenticated else None
    scan = ScanHistory.objects.create(
        user=user,
        mode=ScanHistory.MODE_LITE,
        detected_label=label_key,
        confidence=confidence,
        ripeness_score=rule.ripeness_score,
        ripeness_label=rule.ripeness_label,
        peak_window=rule.peak_window,
        detection_detail=rule.detection_detail,
        quick_tips=rule.quick_tips,
        recommendations=rule.recommendations,
        image_url=rule.reference_image_url,
    )

    result = DetectionRuleSerializer(rule).data
    result['scan_id'] = str(scan.id)
    result['confidence'] = confidence

    return Response(result, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# PRO MODE — Gemini Vision Detection
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([AllowAny])
def detect_pro(request):
    """
    POST /api/detect/pro/

    Receives a base64-encoded image from Flutter.
    Sends it to Gemini Vision API for analysis.
    Returns structured result identical in shape to detect_lite response.

    Request body:
        {
            "image_base64": "<base64 string>",
            "mime_type": "image/jpeg"
        }

    Response:
        Gemini-generated detection result + saved ScanHistory ID
    """
    serializer = ProDetectRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    image_b64 = serializer.validated_data['image_base64']
    mime_type = serializer.validated_data['mime_type']

    # Map MIME type to extension for file storage.
    ext_map = {
        'image/jpeg': 'jpg',
        'image/png': 'png',
        'image/webp': 'webp',
    }
    image_ext = ext_map.get(mime_type, 'jpg')

    # Decode base64 image
    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception:
        return Response(
            {'error': 'Invalid base64 image data'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Persist uploaded image so history/detail endpoints can return image URL.
    image_name = f"scans/pro/{uuid.uuid4().hex}.{image_ext}"
    saved_path = default_storage.save(image_name, ContentFile(image_bytes))
    image_url = default_storage.url(saved_path)

    # Call Gemini Vision
    try:
        gemini_result = gemini_service.analyze_image_pro(image_bytes, mime_type)
    except ValueError as e:
        logger.error(f'Gemini Pro ValueError: {e}')
        return Response({'error': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception as e:
        logger.exception(f'Gemini Pro detection failed with {type(e).__name__}: {e}')
        return Response(
            {'error': f'AI analysis failed: {type(e).__name__}'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # Save to history
    user = request.user if request.user.is_authenticated else None
    scan = ScanHistory.objects.create(
        user=user,
        mode=ScanHistory.MODE_PRO,
        detected_label=gemini_result.get('detected_label', 'Unknown'),
        confidence=gemini_result.get('confidence', 0.0),
        ripeness_score=gemini_result.get('ripeness_score', 0),
        ripeness_label=gemini_result.get('ripeness_label', ''),
        peak_window=gemini_result.get('peak_window', ''),
        detection_detail=gemini_result.get('detection_detail', ''),
        quick_tips=gemini_result.get('quick_tips', []),
        recommendations=gemini_result.get('recommendations', []),
        image_url=image_url,
    )

    gemini_result['scan_id'] = str(scan.id)
    return Response(gemini_result, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# CHATBOT — Both Modes
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([AllowAny])
def chat(request):
    """
    POST /api/chat/

    Handles chatbot messages for both Lite and Pro modes.
    Uses Gemini with context injection from the detection result.

    Request body:
        {
            "session_id": "<uuid or null>",   # null = start new session
            "scan_id": "<uuid>",              # link to ScanHistory
            "message": "When should I prune?",
            "mode": "lite",
            "context": { ... detection result ... }  # if session_id null
        }

    Response:
        {
            "session_id": "<uuid>",
            "reply": "You should prune when..."
        }
    """
    serializer = ChatRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    user_message = data.get('message', '')
    mode = data['mode']
    session_id = data.get('session_id')
    scan_id = data.get('scan_id')
    provided_context = data.get('context', {})

    # Get or create chat session
    user = request.user if request.user.is_authenticated else None

    if session_id:
        try:
            session = ChatSession.objects.get(id=session_id)
        except ChatSession.DoesNotExist:
            return Response(
                {'error': 'Chat session not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
    else:
        # New session — build context from scan or from provided context
        context_data = provided_context
        context_label = provided_context.get('detected_label', '')

        # Build a templated first message when starting a new session
        # Use scan/model/labels to match client-requested phrasing
        initial_prompt = None

        if scan_id:
            try:
                scan = ScanHistory.objects.get(id=scan_id)
                context_data = {
                    'detected_label': scan.detected_label,
                    'confidence': scan.confidence,
                    'ripeness_score': scan.ripeness_score,
                    'ripeness_label': scan.ripeness_label,
                    'peak_window': scan.peak_window,
                    'detection_detail': scan.detection_detail,
                    'quick_tips': scan.quick_tips,
                    'recommendations': scan.recommendations,
                }
                context_label = scan.detected_label

                model_name = provided_context.get('model_name') or "selected model"
                initial_prompt = _build_initial_prompt_for_scan(scan, mode, model_name)
            except ScanHistory.DoesNotExist:
                pass

        # If we built a first-message template, replace the incoming message
        if initial_prompt:
            user_message = initial_prompt

        try:
            session = ChatSession.objects.create(
                user=user,
                mode=mode,
                context_label=context_label,
                context_data=context_data,
                scan_id=scan_id,
            )
        except IntegrityError:
            return Response(
                {
                    'error': 'Chat session already exists for this scan_id.',
                    'hint': 'Reuse the existing session_id returned on the first /api/chat/ call.',
                },
                status=status.HTTP_409_CONFLICT,
            )

    # Load conversation history for Gemini multi-turn
    history_msgs = session.messages.order_by('timestamp')
    history = [
        {'role': 'user' if m.role == 'user' else 'model', 'content': m.content}
        for m in history_msgs
    ]

    # Call Gemini
    try:
        reply = gemini_service.chat_with_gemini(
            user_message=user_message,
            mode=session.mode,
            context=session.context_data,
            history=history,
        )
    except Exception as e:
        logger.exception('Gemini chat failed')
        return Response(
            {'error': 'Chat service unavailable. Please try again.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # Save both messages
    ChatMessage.objects.create(session=session, role='user', content=user_message)
    ChatMessage.objects.create(session=session, role='assistant', content=reply)

    return Response({
        'session_id': str(session.id),
        'reply': reply,
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def chat_initial_message(request):
    """
    GET /api/chat/initial-message/?scan_id=<uuid>&mode=pro&model_name=Apple

    Returns the auto-generated first message for a new chat session.
    """
    scan_id = request.query_params.get('scan_id')
    mode = request.query_params.get('mode')
    model_name = request.query_params.get('model_name') or "selected model"

    if not scan_id:
        return Response(
            {'error': 'scan_id is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    scan = get_object_or_404(ScanHistory, id=scan_id)
    if mode not in (ScanHistory.MODE_LITE, ScanHistory.MODE_PRO):
        mode = scan.mode

    message = _build_initial_prompt_for_scan(scan, mode, model_name)

    return Response({'message': message}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# TFLITE MODEL VERSION CHECK — OTA Model Delivery
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([AllowAny])
def model_version(request):
    """
    GET /api/model/version/

    Returns the currently active TFLite model release.
    The Flutter app calls this endpoint on startup to check whether its
    locally cached model version matches the server's active version.

    Response (active release exists):
        HTTP 200
        {
            "version": "v1.2.0",
            "model_file_url": "https://api.example.com/media/models/v1.2.0/model.tflite",
            "labels_file_url": "https://api.example.com/media/models/v1.2.0/labels.txt",
            "changelog": "Added Apple and Plum detection support.",
            "uploaded_at": "2026-04-15T10:00:00Z"
        }

    Response (no model uploaded yet):
        HTTP 204  No Content

    Flutter integration notes:
      - Cache the version string in SharedPreferences.
      - On mismatch: download model_file_url → save to app documents directory.
      - On mismatch: download labels_file_url → save alongside the model file.
      - Load TFLite interpreter from the locally cached file path.
    """
    try:
        release = TFLiteModel.objects.get(is_active=True)
    except TFLiteModel.DoesNotExist:
        # No model uploaded yet — Flutter should use its bundled fallback model.
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = TFLiteModelSerializer(release, context={'request': request})
    return Response(serializer.data, status=status.HTTP_200_OK)




@api_view(['GET'])
@permission_classes([AllowAny])
def models_list(request):
    """
    GET /api/models/

    Returns all plant categories (for the Models screen in the app).
    Each item shows name, accuracy, latency, and available modes.
    """
    categories = PlantCategory.objects.prefetch_related('labels').all()
    serializer = PlantCategorySerializer(categories, many=True)
    return Response(serializer.data)


# ---------------------------------------------------------------------------
# SCAN HISTORY
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([AllowAny])
def scan_history(request):
    """
    GET /api/history/

    Returns paginated scan history for the current user (or all if anonymous).
    """
    user = request.user if request.user.is_authenticated else None

    if user:
        scans = ScanHistory.objects.filter(user=user)
    else:
        # Anonymous: return last 20 scans (no user filtering)
        scans = ScanHistory.objects.all()[:20]

    serializer = ScanHistorySerializer(scans, many=True)
    data = serializer.data
    base_url = request.build_absolute_uri('/')

    for item in data:
        image_url = item.get('image_url')
        if image_url:
            item['image_full_url'] = image_url if image_url.startswith('http') else request.build_absolute_uri(image_url)
        else:
            item['image_full_url'] = None
        item['base_url'] = base_url

    return Response(data)


@api_view(['GET'])
@permission_classes([AllowAny])
def scan_detail(request, scan_id):
    """
    GET /api/history/<scan_id>/

    Returns a single scan result with its chat session if it exists.
    """
    scan = get_object_or_404(ScanHistory, id=scan_id)
    serializer = ScanHistorySerializer(scan)
    data = serializer.data
    base_url = request.build_absolute_uri('/')

    image_url = data.get('image_url')
    if image_url:
        data['image_full_url'] = image_url if image_url.startswith('http') else request.build_absolute_uri(image_url)
    else:
        data['image_full_url'] = None
    data['base_url'] = base_url

    # Include chat session ID if exists
    try:
        data['chat_session_id'] = str(scan.chat_session.id)
    except ChatSession.DoesNotExist:
        data['chat_session_id'] = None

    return Response(data)


# ---------------------------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    """GET /api/health/ — Simple health check endpoint."""
    from django.conf import settings
    active_model = TFLiteModel.objects.filter(is_active=True).values_list('version', flat=True).first()
    return Response({
        'status': 'ok',
        'service': 'Proon AI Backend',
        'version': '1.1.0',
        'gemini_configured': bool(settings.GEMINI_API_KEY),
        'active_tflite_version': active_model or 'none',
    })


import requests

@api_view(['POST'])
@permission_classes([AllowAny])
def detect_pro_from_url(request):
    serializer = ProDetectUrlRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    image_file = serializer.validated_data['image_file']
    mime_type = serializer.validated_data['mime_type']

    # Read bytes from uploaded file
    image_bytes = image_file.read()

    # Resize/recompress before storage and upstream AI call.
    try:
        image_bytes, mime_type = _resize_image_bytes(image_bytes, mime_type)
    except ValueError:
        return Response({'error': 'Invalid image file'}, status=status.HTTP_400_BAD_REQUEST)

    # Save file (optional, for history URL)
    ext_map = {
        'image/jpeg': 'jpg',
        'image/png': 'png',
        'image/webp': 'webp',
    }
    image_ext = ext_map.get(mime_type, 'jpg')
    image_name = f"scans/pro/{uuid.uuid4().hex}.{image_ext}"
    saved_path = default_storage.save(image_name, ContentFile(image_bytes))
    image_url = request.build_absolute_uri(default_storage.url(saved_path))

    # Reuse existing Pro pipeline
    try:
        gemini_result = gemini_service.analyze_image_pro(image_bytes, mime_type)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    user = request.user if request.user.is_authenticated else None
    scan = ScanHistory.objects.create(
        user=user,
        mode=ScanHistory.MODE_PRO,
        detected_label=gemini_result.get('detected_label', 'Unknown'),
        confidence=gemini_result.get('confidence', 0.0),
        ripeness_score=gemini_result.get('ripeness_score', 0),
        ripeness_label=gemini_result.get('ripeness_label', ''),
        peak_window=gemini_result.get('peak_window', ''),
        detection_detail=gemini_result.get('detection_detail', ''),
        quick_tips=gemini_result.get('quick_tips', []),
        recommendations=gemini_result.get('recommendations', []),
        image_url=image_url,
    )

    gemini_result['scan_id'] = str(scan.id)
    return Response(gemini_result, status=status.HTTP_200_OK)