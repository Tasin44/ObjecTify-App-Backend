from django.urls import path
from . import views

urlpatterns = [
    # Health check
    path('health/', views.health, name='health'),

    # OTA TFLite model delivery
    path('model/version/', views.model_version, name='model-version'),

    # Detection
    path('detect/lite/', views.detect_lite, name='detect-lite'),
    path('detect/pro/', views.detect_pro, name='detect-pro'),

    # Chatbot
    path('chat/', views.chat, name='chat'),

    # Plant models list (for Models screen)
    path('models/', views.models_list, name='models-list'),

    # Scan history
    path('history/', views.scan_history, name='history'),
    path('history/<uuid:scan_id>/', views.scan_detail, name='scan-detail'),
]
