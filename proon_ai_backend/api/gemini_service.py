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


def _build_no_identification_result() -> dict:
    """Return the client-requested response when nothing is identified."""
    return {
        "detected_label": "Unknown",
        "confidence": 0.0,
        "ripeness_score": 0,
        "ripeness_label": "Unknown",
        "peak_window": "Retake photo",
        "status": "Unclassified",
        "quick_tips": [
            "Remove dead wood branches",
            "Retake the photo",
        ],
        "detection_detail": (
            "No clear pruning target was identified in this image."
        ),
        "recommendations": [
            "Please remove all dead wood branches and retake photo."
        ],
    }


def analyze_image_pro(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Pro mode: sends image to the Apple Pruner Cloud API and gets detection results.
    Returns:
        dict matching the DetectionRule / ScanHistory structure.
    """
    import base64
    import ast
    import requests

    if mime_type not in SUPPORTED_MIME_TYPES:
        logger.error("Unsupported MIME type: %s", mime_type)
        return _build_error_result(f"unsupported image type: {mime_type}")

    if len(image_bytes) > MAX_IMAGE_BYTES:
        logger.error("Image too large: %d bytes", len(image_bytes))
        return _build_error_result("image exceeds 10 MB size limit")

    if len(image_bytes) < 100:
        logger.error("Image suspiciously small: %d bytes", len(image_bytes))
        return _build_error_result("image data appears to be empty or corrupt")

    try:
        b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        response = requests.post(
            "https://apple-pruner-api-34w2yszeuq-ez.a.run.app",
            headers={"Content-Type": "application/json"},
            json={"instances": [{"content": b64}]},
            timeout=30
        )

        if response.status_code != 200:
            logger.error("Cloud API returned %s: %s", response.status_code, response.text)
            if response.status_code == 400 and "traffic_split" in response.text:
                logger.warning("Cloud endpoint misconfigured; falling back to Gemini vision.")
                return _analyze_with_gemini_vision(image_bytes, mime_type)
            return _build_error_result(f"Cloud API returned HTTP {response.status_code}")
             
        data = response.json()
        logger.info("Cloud API raw response: %s", response.text)

        predictions = data.get("predictions", [])
        if not predictions:
            return _build_error_result("No predictions returned")

        raw = predictions[0]
        
        confidences = raw.get("confidences", [])
        names = raw.get("displayNames", [])
        bboxes = raw.get("bboxes", [])
        
        if not confidences or not names:
            return _build_no_identification_result()
            
        best_idx = max(range(len(confidences)), key=lambda i: confidences[i])
        best_conf = float(confidences[best_idx])
        best_label = names[best_idx]


        # Client pruning guidance mapped to detection labels
        label_key = str(best_label).strip().lower()
        label_guidance = {
            "leader": {
                "quick_tips": [
                    "Shorten the main leader to control height",
                    "Keep the cut clean and angled",
                ],
                "recommendations": [
                    "Principal branch. Depending on orchard type, you may need to shorten it to control height."
                ],
                "peak_window": "Prune to manage height",
            },
            "secondary": {
                "quick_tips": [
                    "Shorten moderately; avoid aggressive cuts",
                    "Preserve main fruit-bearing branches",
                ],
                "recommendations": [
                    "Main fruit-bearing branches. Shorten them moderately; do not prune aggressively."
                ],
                "peak_window": "Moderate shortening only",
            },
            "transfer_cut": {
                "quick_tips": [
                    "Cut above outward-facing buds",
                    "Guide growth away from the center",
                ],
                "recommendations": [
                    "Cut above buds facing outward. This directs growth away from the center and encourages fruit bud creation."
                ],
                "peak_window": "Target outward buds",
            },
            "water_sprout": {
                "quick_tips": [
                    "Prune vertical shoots immediately",
                    "Remove energy-draining growth",
                ],
                "recommendations": [
                    "Prune immediately. These vertical shoots drain energy and rarely produce fruit."
                ],
                "peak_window": "Prune immediately",
            },
            "competitive_branch": {
                "quick_tips": [
                    "Remove the branch shading the center",
                    "Open the canopy for airflow",
                ],
                "recommendations": [
                    "Prune the one shadowing the tree center. The canopy needs airflow and light."
                ],
                "peak_window": "Open canopy",
            },
        }

        guidance = label_guidance.get(label_key)
        if guidance is None:
            quick_tips = [f"Prune {best_label} as recommended."]
            recommendations = ["Review the identified classes and prune accordingly."]
            peak_window = "N/A"
        else:
            quick_tips = guidance["quick_tips"]
            recommendations = guidance["recommendations"]
            peak_window = guidance["peak_window"]

        result = {
            "detected_label": best_label,
            "confidence": best_conf,
            "ripeness_score": int(best_conf * 100),
            "ripeness_label": "Identified",
            #"peak_window": "N/A",
            "status": "Classified",
            #"quick_tips": [f"Prune {best_label} as recommended."],
            "detection_detail": f"Detected objects: {', '.join(set(names))}.",
            #"recommendations": ["Review the identified classes and prune accordingly."],
            "peak_window": peak_window,
            "quick_tips": quick_tips,
            "recommendations": recommendations,
        }
        
        # Inject the raw prediction arrays so they are mapped directly to ProDetect response
        result["bboxes"] = bboxes
        result["displayNames"] = names
        result["confidences"] = confidences
        
        logger.info("Cloud API Vision: detected '%s' with confidence=%.2f", best_label, best_conf)
        return result

    except Exception as exc:
        logger.exception("Cloud model vision call failed: %s", exc)
        return _build_error_result(f"AI service error: {type(exc).__name__}")


def _analyze_with_gemini_vision(image_bytes: bytes, mime_type: str) -> dict:
    """Fallback vision pipeline using Gemini when the Cloud endpoint is unavailable."""
    from google.genai import types

    try:
        client = _get_client()
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part(text=PRO_VISION_SYSTEM_PROMPT),
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ],
            )
        ]

        raw_text = _call_with_retry(
            client=client,
            model=GEMINI_PRIMARY,
            contents=contents,
            fallback_model=GEMINI_FALLBACK,
        )

        cleaned = _strip_json_fences(raw_text)
        parsed = json.loads(cleaned)
        return _validate_vision_result(parsed)

    except Exception as exc:
        logger.exception("Gemini vision fallback failed: %s", exc)
        return _build_error_result(f"AI service error: {type(exc).__name__}")


# ---------------------------------------------------------------------------
# CHATBOT — Both Modes (Lite & Pro)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Comprehensive pruning knowledge base for every detectable branch label.
# This is injected into the chat system prompt so Gemini can give thorough,
# expert guidance for ALL identified labels — not just one.
# ---------------------------------------------------------------------------
BRANCH_LABEL_KNOWLEDGE = {
    "water_sprout": {
        "display_name": "Water Sprout",
        "definition": (
            "A water sprout (also called a watersprout or epicormic shoot) is a "
            "vigorous, fast-growing vertical shoot that emerges from latent buds on "
            "older wood — typically on the trunk or major scaffold branches."
        ),
        "action": "Remove immediately by pruning flush to the parent branch.",
        "why": (
            "Water sprouts are unproductive — they rarely bear fruit, they grow "
            "straight up and compete for light and nutrients, and they crowd the "
            "canopy, reducing airflow which increases disease risk (e.g. fire blight, "
            "powdery mildew). Removing them redirects the tree's energy to productive "
            "fruiting wood."
        ),
        "tips": [
            "Cut them as close to the base as possible without leaving a stub.",
            "If there are many, remove the thickest/most vigorous ones first.",
            "Inspect after heavy pruning or topping — these events trigger water sprout growth.",
            "Remove them during the dormant season for cleanest healing, but they can be removed any time.",
        ],
    },
    "leader": {
        "display_name": "Leader (Central Leader)",
        "definition": (
            "The leader is the main, dominant, upward-growing branch that forms the "
            "central axis of the tree. It is the primary structural branch from which "
            "scaffold branches emerge."
        ),
        "action": (
            "Generally, preserve the leader. Shorten it only if you need to control "
            "the tree's overall height or if it has grown excessively beyond the "
            "desired canopy height."
        ),
        "why": (
            "The leader defines the tree's shape and structural strength. Cutting it "
            "unnecessarily can disrupt the tree's natural form and trigger excessive "
            "water sprout growth. However, heading the leader to a desired height is "
            "standard practice in commercial orchards to keep fruit within picking reach."
        ),
        "tips": [
            "If heading the leader, make the cut just above an outward-facing lateral branch.",
            "After heading, select a single replacement leader if one is needed — remove competing shoots.",
            "In central-leader training systems, the leader should be the tallest point of the tree.",
            "For open-vase/centre training systems, the leader is removed early to encourage multiple scaffolds.",
        ],
    },
    "secondary": {
        "display_name": "Secondary Branch",
        "definition": (
            "Secondary branches (also called sub-scaffolds or secondary scaffolds) "
            "grow off the main scaffold branches. They are the primary fruit-bearing "
            "wood and form the bulk of the productive canopy."
        ),
        "action": (
            "Shorten moderately if they are too long or drooping. Avoid aggressive "
            "pruning — these branches carry the majority of your fruit crop."
        ),
        "why": (
            "Secondary branches are essential for fruit production. Over-pruning them "
            "reduces yield significantly. Light thinning and moderate shortening "
            "encourages better fruit size and quality by improving light penetration "
            "and air circulation within the canopy."
        ),
        "tips": [
            "Tip-prune to an outward-facing bud to encourage spreading growth.",
            "Remove any secondaries that cross over other branches or grow back toward the center.",
            "Thin out excess secondaries to maintain good spacing (aim for 15–20 cm apart along the scaffold).",
            "Preserve horizontal secondaries — they fruit better than vertical ones.",
        ],
    },
    "competitive_branch": {
        "display_name": "Competitive Branch",
        "definition": (
            "A competitive branch is one that grows at a similar angle and vigor as "
            "the leader or a scaffold branch, essentially competing with it for "
            "dominance. It often grows nearly vertically alongside the leader."
        ),
        "action": (
            "Remove the competitive branch entirely, or shorten it significantly to "
            "subordinate it to the dominant branch it is competing with."
        ),
        "why": (
            "Two branches competing for the same space create a weak crotch angle, "
            "shade the tree's interior, and waste energy. The narrow crotch can split "
            "under fruit load or wind. Removing the competitor strengthens the "
            "remaining branch and opens the canopy for light and airflow."
        ),
        "tips": [
            "Between two competing branches, keep the one with the better crotch angle (ideally 45–60°).",
            "If both are similar, keep the one growing in a direction that balances the canopy.",
            "Make the cut clean, just outside the branch collar — do not leave a stub.",
            "If the competitive branch has good fruit wood, consider subordinating it (shortening by 1/3) instead of removing entirely.",
        ],
    },
    "lateral": {
        "display_name": "Lateral Branch",
        "definition": (
            "A lateral is any side branch growing off a larger branch. In fruit trees, "
            "laterals are where fruit spurs develop and fruit is produced."
        ),
        "action": (
            "Retain productive laterals. Thin out crowded, crossing, or downward-growing "
            "laterals. Tip-prune long laterals to encourage branching and spur formation."
        ),
        "why": (
            "Laterals are the workhorse of fruit production. Proper management ensures "
            "good light distribution, prevents overcrowding, and encourages the "
            "development of fruiting spurs."
        ),
        "tips": [
            "Keep laterals that grow outward and slightly upward for best fruit production.",
            "Remove laterals that hang straight down — they produce poor-quality fruit.",
            "Space laterals evenly around the branch for balanced light exposure.",
        ],
    },
    "scaffold": {
        "display_name": "Scaffold Branch",
        "definition": (
            "Scaffold branches are the main structural limbs that radiate from the "
            "trunk or leader. They form the permanent framework of the tree."
        ),
        "action": (
            "Preserve scaffolds. Only prune to correct structure, remove damaged wood, "
            "or reduce length if they are extending too far."
        ),
        "why": (
            "Scaffolds are the tree's skeleton — losing one means losing a large "
            "portion of the canopy and years of growth. Pruning scaffolds should be "
            "done conservatively and deliberately."
        ),
        "tips": [
            "Ideal scaffold angle is 45–60° from the trunk for strength and productivity.",
            "Maintain 3–5 well-spaced scaffolds for a balanced, open canopy.",
            "Never remove more than one major scaffold in a single season.",
        ],
    },
    "spur": {
        "display_name": "Fruiting Spur",
        "definition": (
            "A spur is a short, stubby twig (usually 1–5 cm) that produces fruit "
            "buds. Spurs are the primary fruiting structures on many fruit trees "
            "(apple, pear, cherry, almond)."
        ),
        "action": (
            "Preserve healthy spurs. Thin out old, unproductive, or overcrowded spurs "
            "to improve fruit size and quality."
        ),
        "why": (
            "Spurs produce your fruit. Overcrowded spurs lead to small, poor-quality "
            "fruit. Thinning spurs allows the tree to put more energy into fewer, "
            "larger, higher-quality fruits."
        ),
        "tips": [
            "On older trees, thin spur clusters to 2–3 buds per cluster.",
            "Remove spurs on the underside of branches — they get the least light.",
            "Some varieties are 'tip bearers' not 'spur bearers' — know your variety before spur-pruning.",
        ],
    },
    "sucker": {
        "display_name": "Sucker",
        "definition": (
            "A sucker is a shoot that grows from the rootstock, below the graft union, "
            "or directly from the root system. It is genetically different from the "
            "desired variety."
        ),
        "action": "Remove immediately by tearing or cutting as close to the root origin as possible.",
        "why": (
            "Suckers drain energy from the grafted variety, never produce the desired "
            "fruit, and can eventually overtake the tree if left unchecked. Tearing "
            "(rather than cutting) removes latent buds and reduces regrowth."
        ),
        "tips": [
            "Check below the graft union — any growth there is a sucker.",
            "Remove suckers as soon as they appear; small ones are easier to tear off.",
            "Avoid damaging the trunk or root bark when removing.",
        ],
    },
    "crossing_branch": {
        "display_name": "Crossing Branch",
        "definition": (
            "A crossing branch grows inward across other branches, rubbing against "
            "them and creating wounds that invite disease."
        ),
        "action": "Remove the crossing branch to prevent rubbing wounds and improve airflow.",
        "why": (
            "Where branches rub, the bark is damaged, creating entry points for fungal "
            "infections and pests. Crossing branches also shade the interior and reduce "
            "air circulation."
        ),
        "tips": [
            "Between two crossing branches, remove the weaker or less well-positioned one.",
            "Make the cut back to the parent branch or to an outward-facing bud.",
        ],
    },
    "dead_branch": {
        "display_name": "Dead Branch (Dead Wood)",
        "definition": (
            "A dead branch is any branch that has died — identifiable by brittle wood, "
            "no buds, peeling bark, or lack of green cambium under the bark."
        ),
        "action": "Remove completely. Cut back to healthy wood or to the branch collar.",
        "why": (
            "Dead wood harbors disease organisms and pests, can break and damage "
            "healthy wood below it, and wastes the tree's energy as it tries to "
            "compartmentalize the dead tissue."
        ),
        "tips": [
            "Dead wood can be removed at any time of year — no need to wait for dormancy.",
            "If a large branch is partially dead, cut back to where you see healthy, green cambium.",
            "Sanitize pruning tools after cutting diseased dead wood.",
        ],
    },
    "diseased_branch": {
        "display_name": "Diseased Branch",
        "definition": (
            "A diseased branch shows signs of infection — cankers, discoloration, "
            "oozing sap, wilting, or unusual growths."
        ),
        "action": (
            "Remove by cutting at least 15–30 cm (6–12 inches) below the visible edge of "
            "the infection into clean, healthy wood."
        ),
        "why": (
            "Diseased branches spread infection to the rest of the tree. Prompt removal "
            "limits the spread and protects the overall health of the tree."
        ),
        "tips": [
            "ALWAYS sanitize pruning tools between cuts (10% bleach solution or 70% isopropyl alcohol).",
            "Dispose of diseased wood away from the orchard — do not compost it.",
            "Check for signs of systemic disease (e.g. fire blight) and consult an arborist if unsure.",
        ],
    },
    "epicormic": {
        "display_name": "Epicormic Shoot",
        "definition": (
            "An epicormic shoot grows from dormant buds embedded in the bark of the "
            "trunk or major branches, similar to water sprouts but often triggered by "
            "stress, heavy pruning, or damage."
        ),
        "action": "Remove unless the tree needs regrowth in that area to rebuild canopy.",
        "why": (
            "Like water sprouts, epicormic shoots are typically unproductive and crowd "
            "the canopy. However, after severe storm damage or heavy pruning, a few "
            "well-placed epicormic shoots may be retained to rebuild the canopy."
        ),
        "tips": [
            "If retaining one for canopy rebuilding, choose the best-positioned shoot and remove the rest.",
            "Monitor annually — they tend to regrow.",
        ],
    },
    "transfer_cut": {
        "display_name": "Transfer Cut",
        "definition": (
            "A transfer cut is a pruning technique where you cut a branch back to a "
            "lateral branch or outward-facing bud to redirect growth in a desired "
            "direction."
        ),
        "action": (
            "Make the cut just above an outward-facing bud or lateral branch to direct "
            "new growth away from the tree's center."
        ),
        "why": (
            "Transfer cuts shape the tree and encourage an open canopy. By cutting to "
            "an outward-facing bud, you direct new growth outward, improving light "
            "penetration and air circulation."
        ),
        "tips": [
            "Angle the cut slightly away from the bud to prevent water pooling on the bud.",
            "Choose a bud that points in the direction you want new growth to go.",
            "Transfer cuts are especially useful for reshaping overgrown trees.",
        ],
    },
}


# fmt: off
_CHAT_SYSTEM_BASE = """\
You are Proon AI — a friendly, expert pruning and plant care assistant.

SCAN CONTEXT
=============================================================
Plant:         {detected_label}
Detection:     {detection_detail}
{tips_section}
{detail_section}

PRUNING KNOWLEDGE FOR IDENTIFIED LABELS
=============================================================
{labels_knowledge}

INSTRUCTIONS
============
- This is the user's first message after scanning their plant. They have identified
  specific branch types and are asking how to proceed.
- You MUST provide detailed, expert pruning guidance for EVERY label/branch type the
  user mentions. Do not skip any. Do not just pick one to talk about.
- For EACH identified label, explain:
    1. What it is (brief definition)
    2. What action to take (prune, keep, shorten, etc.)
    3. Why that action is important
    4. Practical tips for doing it correctly
- Structure your response clearly — use the label name as a heading or introductory
  phrase for each section so the user can follow along easily.
- After addressing all labels, provide a brief overall summary or priority order
  (e.g., "Start by removing the water sprouts first, then address the competitive branch...").
- Be warm, practical, and expert. Write as if you are a seasoned orchardist mentoring
  the user through their pruning session.
- Use plain text (no markdown, no bullet symbols like * or -). Use line breaks and
  spacing to organize your response since the app renders plain text.
- Aim for a thorough, comprehensive response. Do not be brief or vague. The user
  expects detailed, professional-level guidance.
- If the question is unrelated to plants, pruning, or gardening, politely redirect.
"""
# fmt: on

_LITE_TIPS_SECTION = """\
Quick tips:
{tips_formatted}"""

_PRO_TIPS_SECTION = """
"""


def _extract_labels_from_detection_detail(detection_detail: str) -> list:
    """Extract individual label names from a detection_detail string like 'Detected objects: water_sprout, leader, secondary'."""
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


def _extract_labels_from_text(text: str) -> list:
    """Extract individual label names from text based on known keys."""
    if not text:
        return []
    text_lower = text.lower()
    found = []
    for label_key in BRANCH_LABEL_KNOWLEDGE.keys():
        if label_key in text_lower or label_key.replace('_', ' ') in text_lower:
            found.append(label_key)
    return found


def _build_labels_knowledge_section(labels: list) -> str:
    """Build a detailed knowledge section for all identified labels."""
    if not labels:
        return "No specific branch labels identified."

    sections = []
    # Use a set to avoid duplicate sections if a label was extracted multiple ways
    seen = set()
    for label in labels:
        label_key = label.strip().lower().replace(" ", "_")
        if label_key in seen:
            continue
        seen.add(label_key)
        
        knowledge = BRANCH_LABEL_KNOWLEDGE.get(label_key)
        if knowledge:
            tips_text = "\n".join(f"  - {t}" for t in knowledge.get("tips", []))
            section = (
                f"{knowledge['display_name']}\n"
                f"  Definition: {knowledge['definition']}\n"
                f"  Action: {knowledge['action']}\n"
                f"  Why: {knowledge['why']}\n"
                f"  Tips:\n{tips_text}"
            )
            sections.append(section)
        else:
            sections.append(
                f"{label}\n"
                f"  No specific guidance available for this label. "
                f"Provide general pruning best practices."
            )

    return "\n\n".join(sections)


def _build_chat_system_prompt(mode: str, context: dict, user_message: str = "") -> str:
    """Compose the system prompt string for a chat session."""
    tips = context.get("quick_tips", [])
    tips_formatted = "\n".join(f"  - {t}" for t in tips) if tips else "  - No tips available"

    if mode == "lite":
        tips_section = _LITE_TIPS_SECTION.format(
            tips_formatted=tips_formatted,
        )
    else:
        tips_section = _PRO_TIPS_SECTION

    # Extract all detected labels and build knowledge section
    detection_detail = context.get("detection_detail", "")
    labels = _extract_labels_from_detection_detail(detection_detail)
    
    if user_message:
        labels.extend(_extract_labels_from_text(user_message))

    # Also include the primary detected_label if not already in the list
    primary_label = context.get("detected_label", "")
    if primary_label:
        primary_key = primary_label.strip().lower().replace(" ", "_")
        if not any(l.strip().lower().replace(" ", "_") == primary_key for l in labels):
            labels.append(primary_label)

    labels_knowledge = _build_labels_knowledge_section(labels)

    return _CHAT_SYSTEM_BASE.format(
        detected_label=context.get("detected_label", "Unknown plant"),
        detection_detail=detection_detail or "Not available",
        tips_section=tips_section,
        detail_section="",
        labels_knowledge=labels_knowledge,
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
        system_prompt = _build_chat_system_prompt(mode, context, user_message)
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
