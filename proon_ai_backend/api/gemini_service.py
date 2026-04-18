"""
Proon AI — Gemini Service
=========================
All Google Gemini API interactions live here. Nothing else should call
google-genai directly; everything goes through this module.

Responsibilities:
  - Pro mode: plant image → vision analysis → structured JSON result
  - Both modes: chatbot with per-session context injection

SDK: google-genai >= 1.0  (replaces deprecated google-generativeai)
Models:
  - gemini-2.5-flash  ← default; best quality / free tier
  - gemini-2.0-flash  ← fallback when 2.5 quota hits
"""

import json
import re
import time
import logging
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model constants — change here, affects everything
# ---------------------------------------------------------------------------
GEMINI_PRIMARY = "gemini-2.5-flash"      # Used for both vision + chat
GEMINI_FALLBACK = "gemini-2.0-flash"     # Quota relief

# Retry config
MAX_RETRIES = 2          # How many times to retry a failed Gemini call
RETRY_DELAY_SEC = 1.5    # Seconds between retries

# Maximum image size we'll send to Gemini (10 MB decoded bytes)
MAX_IMAGE_BYTES = 10 * 1024 * 1024

SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


# ---------------------------------------------------------------------------
# Internal: SDK client
# ---------------------------------------------------------------------------

def _get_client():
    """Return a configured google.genai Client. Raises clear errors on misconfiguration."""
    try:
        from google import genai
    except ImportError:
        raise ImportError(
            "google-genai is not installed. Run:  pip install google-genai"
        )

    api_key = getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Add it to your .env file and restart the server."
        )

    return genai.Client(api_key=api_key)


def _call_with_retry(client, model: str, contents, fallback_model: Optional[str] = None) -> str:
    """
    Call client.models.generate_content with automatic retry + optional model fallback.

    Returns:
        Raw text string from Gemini.

    Raises:
        Exception: After all retries are exhausted.
    """
    from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable

    last_exc = None

    for attempt in range(MAX_RETRIES + 1):
        active_model = model
        try:
            response = client.models.generate_content(
                model=active_model,
                contents=contents,
            )
            return response.text.strip()

        except (ResourceExhausted,) as exc:
            last_exc = exc
            # Quota exhausted — try fallback model once, then give up
            if fallback_model and active_model != fallback_model:
                logger.warning(
                    "Quota exhausted on %s, switching to fallback %s",
                    active_model, fallback_model,
                )
                active_model = fallback_model
                try:
                    response = client.models.generate_content(
                        model=active_model,
                        contents=contents,
                    )
                    return response.text.strip()
                except Exception as fallback_exc:
                    last_exc = fallback_exc
            break  # Don't retry quota errors multiple times

        except (ServiceUnavailable,) as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                logger.warning("Gemini service unavailable (attempt %d/%d). Retrying...", attempt + 1, MAX_RETRIES)
                time.sleep(RETRY_DELAY_SEC * (attempt + 1))
            else:
                break

        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                logger.warning("Gemini call failed (attempt %d/%d): %s", attempt + 1, MAX_RETRIES, exc)
                time.sleep(RETRY_DELAY_SEC)
            else:
                break

    raise last_exc


def _strip_json_fences(text: str) -> str:
    """Strip markdown code fences that Gemini sometimes wraps around JSON."""
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    return text.strip()


# ---------------------------------------------------------------------------
# PRO MODE — Vision Analysis
# ---------------------------------------------------------------------------

# fmt: off
PRO_VISION_SYSTEM_PROMPT = """\
You are Proon AI — an expert horticultural assistant specialised in plant health,
ripeness detection, and pruning guidance.

TASK
====
Analyse the provided plant image. Return ONLY a valid JSON object — no markdown,
no explanatory text, nothing outside the JSON.

OUTPUT SCHEMA (all fields are required)
========================================
{
  "detected_label": "<concise label, e.g. 'Brussels Sprouts', 'Apple - Unripe', 'Rose Bush'>",
  "confidence": <float 0.0–1.0>,
  "ripeness_score": <integer 0–100>,
  "ripeness_label": "<one of: Very Low | Low | Medium | High | Very High>",
  "peak_window": "<e.g. 'Harvest within 3–5 days' | 'Prune immediately' | 'Not yet ready'>",
  "status": "Classified",
  "quick_tips": [
    "<actionable tip 1>",
    "<actionable tip 2>",
    "<actionable tip 3>"
  ],
  "detection_detail": "<2–3 sentence expert description of what is visible and its current state>",
  "recommendations": [
    "<specific recommendation 1>",
    "<specific recommendation 2>"
  ]
}

RULES
=====
- Be specific and accurate based entirely on what you SEE in the image.
- If the plant/fruit cannot be clearly identified, set confidence < 0.5 and
  explain the ambiguity in detection_detail.
- quick_tips must be SHORT, actionable one-liners (≤ 12 words each).
- recommendations should be 1–2 sentences of practical expert advice.
- Do NOT fabricate data you cannot observe.
- Return ONLY the JSON object. No preamble. No suffix.
"""
# fmt: on


def _validate_vision_result(result: dict) -> dict:
    """
    Validate that all required keys are present and types are correct.
    Fills in safe defaults for optional/formattable fields.
    Raises ValueError if the result is critically malformed.
    """
    required_keys = {
        "detected_label", "confidence", "ripeness_score",
        "ripeness_label", "peak_window", "quick_tips",
        "detection_detail", "recommendations",
    }
    missing = required_keys - result.keys()
    if missing:
        raise ValueError(f"Gemini response missing required fields: {missing}")

    # Type coercions (Gemini sometimes returns strings for numbers)
    try:
        result["confidence"] = float(result["confidence"])
        result["ripeness_score"] = int(result["ripeness_score"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric field in Gemini response: {exc}")

    # Clamp ranges
    result["confidence"] = max(0.0, min(1.0, result["confidence"]))
    result["ripeness_score"] = max(0, min(100, result["ripeness_score"]))

    # Ensure list fields are actually lists
    for list_field in ("quick_tips", "recommendations"):
        if not isinstance(result[list_field], list):
            result[list_field] = [str(result[list_field])]

    # Ensure status key exists
    result.setdefault("status", "Classified")

    return result


def _build_error_result(reason: str = "Analysis failed") -> dict:
    """Return a safe fallback result when Gemini cannot produce a valid response."""
    return {
        "detected_label": "Unknown",
        "confidence": 0.0,
        "ripeness_score": 0,
        "ripeness_label": "Unknown",
        "peak_window": "Unable to analyse",
        "status": "Unclassified",
        "quick_tips": [
            "Retake the photo with better lighting",
            "Ensure the plant fills most of the frame",
            "Try again if the issue persists",
        ],
        "detection_detail": (
            f"The AI could not clearly analyse this image ({reason}). "
            "Please retake the photo with better lighting and focus and try again."
        ),
        "recommendations": [
            "Use natural daylight for best results",
            "Hold the camera steady and close to the subject",
        ],
    }


def analyze_image_pro(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Pro mode: send an image to Gemini Vision and get a structured detection result.

    Args:
        image_bytes: Raw image bytes (decoded, not base64).
        mime_type:   MIME type — must be one of image/jpeg, image/png, image/webp.

    Returns:
        dict matching the DetectionRule / ScanHistory structure.

    Notes:
        - Validates image size and MIME type before sending.
        - Retries on transient Gemini errors.
        - Falls back gracefully; NEVER raises to the caller.
    """
    from google import genai
    from google.genai import types

    # --- Pre-flight validation ---
    if mime_type not in SUPPORTED_MIME_TYPES:
        logger.error("Unsupported MIME type: %s", mime_type)
        return _build_error_result(f"unsupported image type: {mime_type}")

    if len(image_bytes) > MAX_IMAGE_BYTES:
        logger.error("Image too large: %d bytes", len(image_bytes))
        return _build_error_result("image exceeds 10 MB size limit")

    if len(image_bytes) < 100:
        logger.error("Image suspiciously small: %d bytes", len(image_bytes))
        return _build_error_result("image data appears to be empty or corrupt")

    # --- Gemini call ---
    try:
        client = _get_client()
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

        raw_text = _call_with_retry(
            client=client,
            model=GEMINI_PRIMARY,
            contents=[PRO_VISION_SYSTEM_PROMPT, image_part],
            fallback_model=GEMINI_FALLBACK,
        )

        clean_text = _strip_json_fences(raw_text)
        result = json.loads(clean_text)
        result = _validate_vision_result(result)

        logger.info(
            "Pro vision: detected '%s' with confidence=%.2f",
            result.get("detected_label"), result.get("confidence"),
        )
        return result

    except json.JSONDecodeError as exc:
        logger.error("Gemini returned invalid JSON: %s", exc)
        return _build_error_result("AI returned unparseable response")

    except ValueError as exc:
        logger.error("Gemini response validation failed: %s", exc)
        return _build_error_result(str(exc))

    except Exception as exc:
        logger.exception("Gemini vision call failed: %s", exc)
        # Include the actual exception details for debugging
        error_msg = f"AI service error: {type(exc).__name__}"
        return _build_error_result(error_msg)


# ---------------------------------------------------------------------------
# CHATBOT — Both Modes (Lite & Pro)
# ---------------------------------------------------------------------------

# fmt: off
_CHAT_SYSTEM_BASE = """\
You are Proon AI — a friendly, knowledgeable plant care and pruning assistant.

SCAN CONTEXT (do not repeat this block verbatim to the user)
=============================================================
Plant:         {detected_label}
Ripeness:      {ripeness_label} ({ripeness_score}%)
Peak window:   {peak_window}
{tips_section}
{detail_section}

INSTRUCTIONS
============
- Answer the user's question concisely and helpfully, drawing on the scan context above.
- If the question is unrelated to plants, pruning, or gardening, politely redirect.
- Do NOT read out the full scan summary unless the user explicitly asks.
- Keep responses under 150 words unless a detailed explanation is requested.
- Use plain text (no markdown) in your replies since the app renders plain text.
- Be warm, expert, and practical.
"""
# fmt: on

_LITE_TIPS_SECTION = """\
Quick tips:
{tips_formatted}
Detection detail: {detection_detail}"""

_PRO_TIPS_SECTION = """\
Detection detail: {detection_detail}"""


def _build_chat_system_prompt(mode: str, context: dict) -> str:
    """Compose the system prompt string for a chat session."""
    tips = context.get("quick_tips", [])
    tips_formatted = "\n".join(f"  • {t}" for t in tips) if tips else "  • No tips available"

    if mode == "lite":
        tips_section = _LITE_TIPS_SECTION.format(
            tips_formatted=tips_formatted,
            detection_detail=context.get("detection_detail", "Not available"),
        )
    else:
        tips_section = _PRO_TIPS_SECTION.format(
            detection_detail=context.get("detection_detail", "Gemini-analysed image"),
        )

    return _CHAT_SYSTEM_BASE.format(
        detected_label=context.get("detected_label", "Unknown plant"),
        ripeness_label=context.get("ripeness_label", "Unknown"),
        ripeness_score=context.get("ripeness_score", 0),
        peak_window=context.get("peak_window", "N/A"),
        tips_section=tips_section,
        detail_section="",  # already embedded in tips_section above
    )


def _build_contents_for_chat(system_prompt: str, history: list, user_message: str):
    """
    Build the contents list for a multi-turn chat Gemini call.

    We inject the system prompt as a priming user→model exchange at the top of
    the conversation so it remains in context throughout the session.

    Args:
        system_prompt: Full context/instruction prompt string.
        history: List of dicts {'role': 'user'|'assistant', 'content': '...'}.
                 This should NOT include the new user_message.
        user_message: The current user's message.

    Returns:
        List of types.Content objects.
    """
    from google.genai import types

    contents = [
        # Priming exchange — establishes persona + context
        types.Content(
            role="user",
            parts=[types.Part(text=system_prompt)],
        ),
        types.Content(
            role="model",
            parts=[types.Part(
                text=(
                    "Understood! I'm Proon AI, ready to help you with questions about "
                    "your plant scan and general care guidance."
                )
            )],
        ),
    ]

    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part(text=msg["content"])],
            )
        )

    contents.append(
        types.Content(
            role="user",
            parts=[types.Part(text=user_message)],
        )
    )

    return contents


def chat_with_gemini(
    user_message: str,
    mode: str,
    context: dict,
    history: list,
) -> str:
    """
    Send a chat message to Gemini and receive a reply.

    Args:
        user_message: The user's text input.
        mode:         'lite' or 'pro' — determines prompt style.
        context:      Detection result dict (from Lite rule or Pro vision analysis).
        history:      Previous messages in the session as
                      [{'role': 'user'|'assistant', 'content': '...'}, ...].

    Returns:
        AI reply string. Never raises — returns a polite error message on failure.
    """
    if not user_message or not user_message.strip():
        return "I didn't catch that. Could you please rephrase your question?"

    if mode not in ("lite", "pro"):
        logger.warning("Unknown chat mode '%s', defaulting to 'lite'", mode)
        mode = "lite"

    try:
        client = _get_client()
        system_prompt = _build_chat_system_prompt(mode, context)
        contents = _build_contents_for_chat(system_prompt, history, user_message)

        reply = _call_with_retry(
            client=client,
            model=GEMINI_PRIMARY,
            contents=contents,
            fallback_model=GEMINI_FALLBACK,
        )

        logger.debug("Chat reply generated (%d chars)", len(reply))
        return reply

    except Exception as exc:
        logger.exception("Gemini chat call failed: %s", exc)
        return (
            "I'm having trouble connecting right now. "
            "Please try again in a moment or check your network."
        )
