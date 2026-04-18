# Proon AI — Backend & AI Developer Guide

> **Project:** Proon — Plant Pruning & Ripeness Detection App  
> **Stack:** Django 5 + Django REST Framework + Google Gemini API  
> **Version:** 1.1.0 | April 2026

---

## Overview

Proon is a plant-care app with two scanning modes:

| Mode | Internal Name | Flow |
|------|---------------|------|
| **Lite** | LOCAL | Mobile app → TFLite on-device → `/api/detect/lite/` → Rule-based DB result |
| **Pro** | GLOBAL | Mobile app → `/api/detect/pro/` → Gemini Vision → AI-generated result |
| **Chat** | Both | Mobile app → `/api/chat/` → Gemini Chat → Contextual reply |

**Key principle:** The TFLite model file **runs on the user's phone**. The backend never executes it. The mobile app sends the label/confidence output from TFLite to the backend, which looks up the result card from the database.

---

## How OTA Model Updates Work

> This is the most important architectural concept. Read it before touching anything else.

When the AI developer trains a new, better TFLite model, you do **not** need to publish a new app version to the Play Store or App Store. Instead:

```
AI developer trains new model
         │
         ▼
Admin uploads .tflite + labels.txt via Django Admin
  → Sets version = "v1.2.0", ticks "Is active"
         │
         ▼
GET /api/model/version/ now returns v1.2.0
         │
         ▼
Flutter app (on launch) compares server version vs. cached version
  → Version mismatch → downloads model_file_url + labels_file_url
  → Caches files in app's local documents directory
  → Loads TFLite interpreter from the cached file
         │
         ▼
All 1000+ users silently get the new model on their next app launch.
No app store release. No user action required.
```

**Flutter-side responsibilities (for the mobile developer):**
1. On app launch, call `GET /api/model/version/`.
2. Compare returned `version` against the value stored in `SharedPreferences`.
3. If versions differ (or no local version exists), download `model_file_url` → save to app documents directory.
4. Download `labels_file_url` → save alongside the model.
5. Update `SharedPreferences` with the new version string.
6. Load the TFLite interpreter from the local file path.
7. If `GET /api/model/version/` returns HTTP 204, use the bundled fallback model.

---

## Project Structure

```
proon_ai_backend/
├── manage.py
├── requirements.txt
├── .env.example              ← Copy to .env and fill values
├── proon_ai_backend/
│   ├── settings.py           ← Django config
│   ├── urls.py               ← Root URL routing
│   └── wsgi.py
└── api/
    ├── models.py             ← DB schema (TFLiteModel, PlantCategory, DetectionRule, ScanHistory, Chat*)
    ├── views.py              ← All API endpoint handlers
    ├── serializers.py        ← DRF request/response shapes
    ├── urls.py               ← /api/ URL routing
    ├── admin.py              ← Django admin — including TFLite model upload UI
    ├── gemini_service.py     ← ALL AI logic (Gemini Vision + Chat) — DO NOT modify
    └── management/
        └── commands/
            └── seed_data.py  ← DB seeder (adds initial plant + rule data)
```

---

## Setup (Development)

### 1. Create virtual environment
```bash
cd proon_ai_backend
python -m venv venv
venv\Scripts\activate         # Windows
# source venv/bin/activate    # Mac / Linux
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment variables
```bash
copy .env.example .env        # Windows
# cp .env.example .env        # Mac / Linux
```

Edit `.env`:
```dotenv
DJANGO_SECRET_KEY=<generate a long random string>
DEBUG=True
GEMINI_API_KEY=<get from https://aistudio.google.com/app/apikey>
```

Get a free Gemini API key at: **https://aistudio.google.com/app/apikey**

### 4. Run migrations
```bash
python manage.py migrate
```

### 5. Seed the database
```bash
python manage.py seed_data
```
Creates the initial `Sprouts` plant category and its detection rule. Safe to re-run — uses `update_or_create`.

### 6. Create an admin user
```bash
python manage.py createsuperuser
```

### 7. Start the development server
```bash
python manage.py runserver
```
Server: `http://127.0.0.1:8000`

---

## Uploading a TFLite Model (Admin Workflow)

> **This is the workflow for pushing a model update to all users.**

1. Open Django Admin: `http://127.0.0.1:8000/admin/`
2. Navigate to **TFLite Model Releases** → **Add TFLite Model Release**.
3. Fill in:
   - **Version**: e.g. `v1.2.0` (must be unique, use semantic versioning)
   - **Model file**: upload the `.tflite` file
   - **Labels file**: upload the `labels.txt` file
   - **Changelog**: describe what changed (optional but recommended)
   - **Is active**: tick this checkbox to make it live immediately
4. Click **Save**.

> Ticking "Is active" on one release automatically deactivates all others.  
> Alternatively, use the **Activate** bulk action from the list view.

**To verify it's live:**
```bash
curl http://127.0.0.1:8000/api/model/version/
```
Expected response:
```json
{
  "version": "v1.2.0",
  "model_file_url": "http://127.0.0.1:8000/media/models/v1.2.0/model.tflite",
  "labels_file_url": "http://127.0.0.1:8000/media/models/v1.2.0/labels.txt",
  "changelog": "Added Apple and Plum detection support.",
  "uploaded_at": "2026-04-15T10:00:00Z"
}
```

---

## API Reference

All endpoints accept and return JSON. No authentication required in the current version.

### Health Check
```
GET /api/health/
```
```json
{
  "status": "ok",
  "service": "Proon AI Backend",
  "version": "1.1.0",
  "gemini_configured": true,
  "active_tflite_version": "v1.2.0"
}
```

---

### TFLite Model Version Check (OTA)
```
GET /api/model/version/
```

**Response — active release exists (HTTP 200):**
```json
{
  "version": "v1.2.0",
  "model_file_url": "https://api.example.com/media/models/v1.2.0/model.tflite",
  "labels_file_url": "https://api.example.com/media/models/v1.2.0/labels.txt",
  "changelog": "Added Apple and Plum detection support.",
  "uploaded_at": "2026-04-15T10:00:00Z"
}
```

**Response — no model uploaded yet (HTTP 204):**  
Empty body. Flutter should fall back to its bundled model.

---

### Lite Detection — TFLite result → rule lookup
```
POST /api/detect/lite/
```
**Request:**
```json
{ "label": "Sprouts", "confidence": 0.94 }
```
- `label` must match a `DetectionLabel.label_key` in the database (case-insensitive).
- `confidence` is `0.0–1.0`.

**Response:** Full detection result card + `scan_id` UUID.

---

### Pro Detection — image → Gemini Vision
```
POST /api/detect/pro/
```
**Request:**
```json
{ "image_base64": "<base64 string>", "mime_type": "image/jpeg" }
```
- Supported MIME types: `image/jpeg`, `image/png`, `image/webp`
- Maximum image size: **10 MB** (enforced in `gemini_service.py`)
- The response shape is **identical** to Lite mode so the mobile app uses a single result card component.

**Response:** Gemini-generated detection result + `scan_id`.

---

### Chat
```
POST /api/chat/
```
**Request:**
```json
{
  "session_id": null,
  "scan_id": "<uuid>",
  "message": "When should I prune?",
  "mode": "lite",
  "context": { "...detection result..." }
}
```
- `session_id: null` starts a new session. Subsequent messages pass the returned `session_id`.
- `scan_id` links the chat to a ScanHistory record (used to load context automatically).
- `context` is only needed if `session_id` is null and you don't want to rely on `scan_id` lookup.

**Response:**
```json
{ "session_id": "<uuid>", "reply": "You should prune when..." }
```

---

### Models List
```
GET /api/models/
```
Returns all `PlantCategory` records. Used by the Models screen in the mobile app.

---

### Scan History
```
GET /api/history/           ← Last 20 scans (or user's scans if authenticated)
GET /api/history/<scan_id>/ ← Single scan detail + chat_session_id
```

---

## Django Admin

Access: `http://127.0.0.1:8000/admin/`

| Section | What you manage |
|---|---|
| **TFLite Model Releases** | Upload new model versions, activate/deactivate releases |
| **Plant Categories** | Add new plant types |
| **Detection Labels** | Map TFLite label keys (from `labels.txt`) to plant categories |
| **Detection Rules** | Edit the content shown in Lite mode result cards |
| **Scan History** | View all user scans (read-only recommended) |
| **Chat Sessions / Messages** | View conversations (read-only recommended) |

### Adding a new plant label (when the AI developer delivers a new TFLite model)

1. AI developer provides an updated `labels.txt` with new label names.
2. Admin → **Plant Categories** → Add category (e.g. `Apple`).
3. Admin → **Detection Labels** → Add label key (e.g. `Apple_Ripe`) → link to category.
4. Admin → **Detection Rules** → Add rule for that label (ripeness score, tips, etc.)
5. Upload the new `.tflite` + `labels.txt` as a new TFLite Model Release and activate it.
6. Alternatively: ask the AI developer to update `seed_data.py` with the new entries and re-run `python manage.py seed_data`.

---

## AI Layer — `api/gemini_service.py`

> **Django developer: you do not need to modify this file.**  
> This section is documentation only.

### Key constants (top of file)

| Constant | Default | Purpose |
|---|---|---|
| `GEMINI_PRIMARY` | `gemini-2.5-flash` | Main model for both vision and chat |
| `GEMINI_FALLBACK` | `gemini-2.0-flash` | Auto-switched to if quota is exhausted |
| `MAX_RETRIES` | `2` | Retries on transient errors before failing |
| `RETRY_DELAY_SEC` | `1.5` | Seconds between retries (exponential) |
| `MAX_IMAGE_BYTES` | `10 MB` | Images larger than this are rejected before API call |

### `analyze_image_pro(image_bytes, mime_type)` — Pro mode

1. Validates image size and MIME type.
2. Sends the image + a structured prompt to Gemini Vision.
3. Parses and validates the JSON response (all required keys, numeric type coercion, range clamping).
4. Retries on transient errors; switches to fallback model on quota exhaustion.
5. **Always returns a dict** — never raises. On failure, returns a safe "Unclassified" result with helpful user-facing messages.

### `chat_with_gemini(user_message, mode, context, history)` — Chatbot

1. Builds a context-injected system prompt (different templates for Lite vs. Pro mode).
2. Prepends the system prompt as a priming user→model exchange (Gemini doesn't have a native system role).
3. Appends full conversation history for multi-turn continuity.
4. Retries on transient errors; switches to fallback model on quota.
5. **Always returns a string** — never raises. On failure, returns a polite error message.

### Gemini JSON prompt approach

The Pro vision prompt instructs Gemini to return **only** a JSON object. The service:
- Strips markdown code fences (` ```json ... ``` `) that Gemini sometimes inserts.
- Validates all required keys are present.
- Coerces types (strings → float/int).
- Clamps `confidence` to `[0.0, 1.0]` and `ripeness_score` to `[0, 100]`.

---

## Database Schema Overview

```
TFLiteModel           — Versioned model releases (upload here, Flutter downloads from here)

PlantCategory         — A plant type (e.g. Sprouts, Apple)
  └── DetectionLabel  — TFLite label key (e.g. "Sprouts") → links to category
        └── DetectionRule ← Lite mode result content (ripeness, tips, recommendations)

ScanHistory           — Record of every scan (both Lite and Pro)
  └── ChatSession     — One chat session per scan
        └── ChatMessage  — Individual messages in the chat
```

---

## Deployment (Production)

### PostgreSQL

Uncomment the PostgreSQL block in `settings.py` and comment out SQLite:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT', default='5432'),
    }
}
```

Add to `.env`:
```dotenv
DB_NAME=proon_db
DB_USER=proon_user
DB_PASSWORD=your_password
DB_HOST=your-db-host.example.com
DB_PORT=5432
```

### ⚠️ Media Files in Production

**Whitenoise does NOT serve media files** — it only serves static files (CSS, JS, etc.).  
If you are on a VPS with nginx, add this block to your nginx config:

```nginx
location /media/ {
    alias /path/to/proon_ai_backend/media/;
    # Disable gzip for .tflite — it's already compressed
    gzip off;
    # Cache headers for model files
    location ~* \.tflite$ {
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
}
```

If you are on Railway / Render / Fly.io without persistent disk, use **object storage** (S3, GCS, R2):
- Install `django-storages` + `boto3`
- Point `DEFAULT_FILE_STORAGE` to your S3 backend
- The `model_file_url` returned by `/api/model/version/` will then be a direct S3 URL

### Platform deploy commands (Railway / Render / Fly.io)

```bash
python manage.py migrate
python manage.py seed_data
python manage.py collectstatic --noinput
```

### Procfile (for Railway / Heroku)
```
web: gunicorn proon_ai_backend.wsgi:application --bind 0.0.0.0:$PORT
```

### Environment variables to set on the platform

| Variable | Required | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | ✅ | Generate at https://djecrety.ir |
| `GEMINI_API_KEY` | ✅ | From Google AI Studio |
| `DEBUG` | ✅ | Set to `False` in production |
| `ALLOWED_HOSTS` | ✅ | Your domain(s), comma-separated |
| `DB_NAME` | ✅ (prod) | PostgreSQL database name |
| `DB_USER` | ✅ (prod) | PostgreSQL username |
| `DB_PASSWORD` | ✅ (prod) | PostgreSQL password |
| `DB_HOST` | ✅ (prod) | PostgreSQL host |
| `DB_PORT` | — | Defaults to `5432` |
| `CORS_ALLOW_ALL` | — | Set `False` in prod; use `CORS_ORIGINS` |
| `CORS_ORIGINS` | — | Comma-separated allowed origins |

---

## Open Items / Future Work

| Item | Owner | Notes |
|---|---|---|
| User authentication | Django dev | Endpoints are open. Add token auth when needed. |
| Image storage | Django dev | Pro scans don't store images. Add S3/GCS if history thumbnails needed. |
| Object storage for media | Django dev | Required in production on platforms without persistent disk (Railway, Render, etc.). Use `django-storages` + S3/GCS/R2. |
| New plant labels | AI dev → Django dev | AI dev provides new `seed_data.py` entries + new `.tflite` when client delivers updated models. |
| Rate limiting | Django dev | Add `django-ratelimit` to `/api/detect/pro/` to protect Gemini quota. |
| Chat session expiry | Django dev | Sessions grow indefinitely. Add cleanup task (e.g. delete sessions > 30 days old). |
| Model file size validation | Django dev | Optionally validate that uploaded `.tflite` is not empty or corrupt before activating. |
