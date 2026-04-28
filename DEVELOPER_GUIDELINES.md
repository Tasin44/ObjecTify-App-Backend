# 🚀 Proon AI: Migration Guide (Gemini Vision ➡️ Cloud Object Detection)

This document outlines the recent architectural changes made to the backend and the action items required for both **Backend** and **Frontend** developers to successfully integrate the new Cloud Object Detection model.

---

## 🏗️ What Was Changed?

Instead of relying on general-purpose AI (Google Gemini) for plant ripeness analysis, the app now uses a **custom Cloud Vision Model** (Apple Pruner API) for precise object detection. 

1. **Local/Lite Mode:** The backend database was seeded with a new TFLite model (`model.tflite`) and an updated classes file (`water_sprouts_classes.txt`).
2. **Cloud/Pro Mode:** `gemini_service.py` was rewritten to forward base64 image data to the custom cloud endpoint (`https://apple-pruner-api-34w2yszeuq-ez.a.run.app`). The API now returns object coordinates (bounding boxes), specific labels, and confidence metrics instead of just conversational text.

---

## 🛠️ Action Items for BACKEND Developer

The core migration is already implemented in `proon_ai_backend/api/gemini_service.py` and the database has been seeded. However, there are a few integration wrap-ups:

### 1. Update the `ScanHistory` Database Model (Optional but Recommended)
Currently, `detect_pro` returns bounding boxes (`bboxes`), `displayNames`, and `confidences` to the frontend, but it **does not** save them to the `ScanHistory` model. 
* **If the app needs to show bounding boxes in the "Scan History" tab:** Add a `JSONField` to `ScanHistory` in `api/models.py` to store the coordinates. Updates to `api/views.py` will be needed to save these lists.

### 2. Verify the Pro Mode JSON Response
When the frontend calls `POST /api/detect/pro/`, the response JSON now contains extra arrays. Make sure your DRF serializers/views allow these pass-throughs:
```json
{
  "detected_label": "water_sprout",
  "confidence": 0.85,
  "status": "Classified",
  "bboxes": [
    [0.10, 0.20, 0.50, 0.60] 
  ],
  "displayNames": ["water_sprout"],
  "confidences": [0.85]
}
```

---

## 📱 Action Items for FRONTEND Developer

The user experience needs to shift from showing "chat context" to **drawing bounding boxes** over the image. 

### 1. Download the New Local Model (Lite Mode)
* On startup, ensure the app successfully hits `GET /api/model/version/`. 
* It should detect the new version (`v2.water_sprouts.0`) and automatically download the new `model.tflite` and `water_sprouts_classes.txt`. No major code changes are required here as long as OTA updates are functioning.

### 2. Parse & Render Bounding Boxes (Pro Mode)
Upon sending an image to `POST /api/detect/pro/`, you will receive `bboxes`, `displayNames`, and `confidences` arrays. You now need to map these normalized dimensions to pixels and draw rectangles over the uploaded image.

**Bounding Box Math (Normalized to Pixels):**
The API returns `bboxes` in the format: `[xmin, xmax, ymin, ymax]`. These are normalized coordinates (`0.0` to `1.0`).

```javascript
// Example formula to render the boxes in the UI
const x_min = bbox[0] * image_width;
const x_max = bbox[1] * image_width;
const y_min = bbox[2] * image_height;
const y_max = bbox[3] * image_height;

const width = x_max - x_min;
const height = y_max - y_min;
```

### 3. Implement the Color-Coding Legend
The custom cloud model has predefined classes. You should assign these specific border colors to the bounding boxes rendered on the screen:

| Label | Color |
| :--- | :--- |
| `leader` | Yellow |
| `fruit_bud` | Pink |
| `water_sprout` | Red |
| `fruit_branch` | Green |
| `secondary` | Blue |
| `transfer_cut` | Orange |
| `competitive_branch` | Purple |

### 4. UI Adjustments
* **Remove Chat/History Expectations:** The previous Gemini implementation returned things like `quick_tips` and `detection_detail`. The new API just passes mock values for these to prevent the app from crashing. 
* **Focus on Visuals:** Update the UI to focus heavily on the image output with the colored boxes, rather than paragraphs of text.