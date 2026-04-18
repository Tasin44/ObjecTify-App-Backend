#!/usr/bin/env python
"""
Quick test to verify Gemini API key and connectivity.
No Unicode characters for Windows compatibility.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'proon_ai_backend.settings')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from django.conf import settings
from decouple import config

print("=" * 70)
print("GEMINI API KEY DIAGNOSTIC")
print("=" * 70)

# Step 1: Check if API key is loaded
api_key = getattr(settings, 'GEMINI_API_KEY', '')
print("\n1. API Key Status:")
print(f"   Found: {bool(api_key)}")
if api_key:
    print(f"   Length: {len(api_key)} chars")
    print(f"   Starts with: {api_key[:15]}...")

# Step 2: Check if google-genai is installed
print("\n2. Dependencies:")
try:
    from google import genai
    print("   OK - google-genai: INSTALLED")
except ImportError as e:
    print(f"   FAIL - google-genai: NOT INSTALLED ({e})")
    sys.exit(1)

# Step 3: Try to initialize Gemini client
print("\n3. Gemini Client Initialization:")
try:
    client = genai.Client(api_key=api_key)
    print("   OK - Client created")
except Exception as e:
    print(f"   FAIL - {type(e).__name__}: {e}")
    sys.exit(1)

# Step 4: Test simple text generation
print("\n4. Testing Simple Text Generation:")
try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Say 'Hello'",
    )
    print(f"   OK - Response: {response.text[:50]}")
except Exception as e:
    print(f"   FAIL - {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 5: Test image analysis
print("\n5. Testing Image Analysis (with 1x1 pixel JPEG):")
try:
    from api import gemini_service
    from google.genai import types
    
    # Minimal 1x1 JPEG
    minimal_jpeg = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x01, 0x00, 0x60, 0x00, 0x60, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x14, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0xFF, 0xC4, 0x00, 0x14, 0x10, 0x01, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00,
        0x7F, 0xFF, 0xD9
    ])
    
    result = gemini_service.analyze_image_pro(minimal_jpeg, "image/jpeg")
    
    if result.get('detected_label') != 'Unknown' or 'clearly analyse' in result.get('detection_detail', ''):
        if 'AI service error' in result.get('detection_detail', ''):
            print(f"   FAIL - AI service error: {result.get('detection_detail')}")
        else:
            print(f"   OK - Detected: {result.get('detected_label')}")
    else:
        print(f"   UNKNOWN - {result.get('detection_detail')}")
        
except Exception as e:
    print(f"   FAIL - {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("DONE")
print("=" * 70)
