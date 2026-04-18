#!/usr/bin/env python
"""
Quick test to verify Gemini API key and connectivity.
Run from Django project root: python test_gemini_basic.py
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
api_key_from_config = config('GEMINI_API_KEY', default='')
api_key_from_settings = getattr(settings, 'GEMINI_API_KEY', '')

print(f"\n1. API Key Status:")
print(f"   From .env (decouple): {'[OK] Found' if api_key_from_config else '[FAIL] NOT FOUND'}")
print(f"   From Django settings: {'[OK] Found' if api_key_from_settings else '[FAIL] NOT FOUND'}")

if api_key_from_config:
    print(f"   Length: {len(api_key_from_config)} chars")
    print(f"   Starts with: {api_key_from_config[:10]}...")
    print(f"   Ends with: ...{api_key_from_config[-10:]}")

# Step 2: Check if google-genai is installed
print(f"\n2. Dependencies:")
try:
    from google import genai
    print(f"   ✅ google-genai: INSTALLED")
except ImportError as e:
    print(f"   ❌ google-genai: NOT INSTALLED")
    print(f"      Error: {e}")
    sys.exit(1)

# Step 3: Try to initialize Gemini client
print(f"\n3. Gemini Client Initialization:")
try:
    client = genai.Client(api_key=api_key_from_settings)
    print(f"   ✅ Client created successfully")
except Exception as e:
    print(f"   ❌ Failed to create client")
    print(f"      Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 4: Test simple text generation
print(f"\n4. Testing Simple Text Generation:")
try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Respond with exactly: 'SUCCESS'",
    )
    print(f"   ✅ API call succeeded")
    print(f"   Response: {response.text}")
except Exception as e:
    print(f"   ❌ API call failed")
    print(f"      Error type: {type(e).__name__}")
    print(f"      Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 5: Test from gemini_service module
print(f"\n5. Testing gemini_service.analyze_image_pro (with dummy image):")
try:
    from api import gemini_service
    
    # Create a minimal valid JPEG (1x1 pixel white image)
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
    
    if result.get('detected_label') != 'Unknown':
        print(f"   ✅ Image analysis worked! Detected: {result.get('detected_label')}")
    else:
        print(f"   ⚠️  Got 'Unknown' response (expected with minimal image)")
        print(f"      Detection detail: {result.get('detection_detail')}")
        
except Exception as e:
    print(f"   ❌ gemini_service test failed")
    print(f"      Error: {e}")
    import traceback
    traceback.print_exc()

print(f"\n" + "=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)
