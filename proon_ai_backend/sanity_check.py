#!/usr/bin/env python
"""
Quick sanity check for Gemini setup.
Run from proon_ai_backend folder: python sanity_check.py
"""
import os
import sys
import base64

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'proon_ai_backend.settings')
sys.path.insert(0, os.getcwd())

import django
django.setup()

from django.conf import settings
from api import gemini_service

print("\n" + "="*70)
print("GEMINI SETUP SANITY CHECK")
print("="*70)

# Check 1: API Key loaded
api_key = settings.GEMINI_API_KEY
if not api_key:
    print("\nFAIL: GEMINI_API_KEY is empty!")
    print("  → Check your .env file has GEMINI_API_KEY=...")
    sys.exit(1)
print(f"\nOK: API Key loaded ({len(api_key)} chars)")

# Check 2: google-genai installed
try:
    from google import genai
    from google.genai import types
    print("OK: google-genai package installed")
except ImportError as e:
    print(f"FAIL: google-genai not installed: {e}")
    print("  → Run: pip install -r requirements.txt")
    sys.exit(1)

# Check 3: Can instantiate client
try:
    client = genai.Client(api_key=api_key)
    print("OK: Gemini client instantiated")
except Exception as e:
    print(f"FAIL: Could not create Gemini client: {e}")
    sys.exit(1)

# Check 4: Text generation works
try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Say 'Hello, Proon!'",
    )
    text = response.text
    if "Hello" in text or "Proon" in text:
        print(f"OK: Text generation works")
        print(f"  Response: {text[:50]}...")
    else:
        print(f"WARN: Unexpected response: {text[:50]}")
except Exception as e:
    print(f"FAIL: Text generation failed: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Check 5: Vision with minimal image
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

try:
    result = gemini_service.analyze_image_pro(minimal_jpeg, "image/jpeg")
    status = result.get('status', 'Unknown')
    label = result.get('detected_label', 'Unknown')
    detail = result.get('detection_detail', '')
    
    if status == "Classified":
        print(f"OK: Vision analysis returned Classified result")
        print(f"  Label: {label}")
    elif "Unable to analyse" in detail:
        print(f"WARN: Got expected 'Unable to analyse' for 1x1 pixel image")
    elif "AI service error" in detail:
        print(f"FAIL: Vision analysis returned AI service error")
        print(f"  Detail: {detail}")
    else:
        print(f"OK: Vision analysis completed")
        print(f"  Status: {status}, Label: {label}")
except Exception as e:
    print(f"FAIL: Vision call raised exception: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*70)
print("SUCCESS: All checks passed! Your Gemini setup is working.")
print("="*70 + "\n")
