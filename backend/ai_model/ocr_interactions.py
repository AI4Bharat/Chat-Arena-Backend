import os
import io
import json
import logging
import base64
import requests
from PIL import Image as PILImage
from openai import OpenAI
from ai_model.error_logging import log_and_raise

logger = logging.getLogger(__name__)


# Layout-only prompt — detects regions and bounding boxes without extracting text.
OCR_LAYOUT_PROMPT = """You are a document layout analysis engine. Detect all text and figure regions in this document image.

Return ONLY a valid JSON array (no markdown, no explanation) where each element has:
- "id": a unique string identifier (e.g. "r1", "r2", ...)
- "box_2d": [ymin, xmin, ymax, xmax] — values in [0, 1000] where (0,0) is top-left and (1000,1000) is bottom-right
- "type": one of "title", "heading", "paragraph", "table", "figure", "caption", "list", "other"

Rules:
- box_2d values must be integers in [0, 1000]; ymin < ymax, xmin < xmax
- Each box must FULLY encompass all lines belonging to that region
- Detect every distinct text block and figure in reading order (top-to-bottom, left-to-right)
- Do NOT extract or return any text content"""

# Full OCR prompt — detects regions and transcribes text within each region.
OCR_FULL_PROMPT = """You are a document layout analysis and OCR engine. Detect all text and figure regions in this document image and transcribe the text within each region.

Return ONLY a valid JSON array (no markdown, no explanation) where each element has:
- "id": a unique string identifier (e.g. "r1", "r2", ...)
- "box_2d": [ymin, xmin, ymax, xmax] — values in [0, 1000] where (0,0) is top-left and (1000,1000) is bottom-right
- "type": one of "title", "heading", "paragraph", "table", "figure", "caption", "list", "other"
- "text": the exact text content within this region (empty string "" for figures/images with no text)

Rules:
- box_2d values must be integers in [0, 1000]; ymin < ymax, xmin < xmax
- Each box must FULLY encompass all lines belonging to that region
- Detect every distinct text block and figure in reading order (top-to-bottom, left-to-right)
- Transcribe text exactly as it appears; preserve line breaks within a region using \n
- For figure/image-only regions with no readable text, set "text" to an empty string"""


def _process_ocr_item(item, img_width, img_height, index, generate_text=True):
    """Convert a raw Gemini annotation dict to our internal format."""
    raw_box = item.get('box_2d') or item.get('box', [0, 0, 100, 100])
    has_box_2d = 'box_2d' in item and item['box_2d']

    if isinstance(raw_box, (list, tuple)) and len(raw_box) == 4:
        a, b, c, d = [float(v) for v in raw_box]
        if has_box_2d:
            ymin, xmin, ymax, xmax = a, b, c, d
        else:
            xmin, ymin, xmax, ymax = a, b, c, d

        x1 = int(xmin * img_width / 1000)
        y1 = int(ymin * img_height / 1000)
        x2 = int(xmax * img_width / 1000)
        y2 = int(ymax * img_height / 1000)
        box = [x1, y1, x2, y2]
    else:
        box = [0, 0, img_width // 4, img_height // 4]

    return {
        'id': item.get('id', f'r{index + 1}'),
        'box': box,
        'text': item.get('text', '') if generate_text else '',
        'type': item.get('type', 'paragraph'),
        'page': int(item.get('page', 1)),
    }


def _prepare_gemini_request(image_url, model, generate_text=True):
    """Download image and build the Gemini client + request args. Returns (client, user_content, system_prompt, img_width, img_height)."""
    img_response = requests.get(image_url, timeout=60)
    img_response.raise_for_status()
    image_data = img_response.content
    image_base64 = base64.b64encode(image_data).decode('utf-8')

    from PIL import ImageOps
    pil_img = PILImage.open(io.BytesIO(image_data))
    pil_img = ImageOps.exif_transpose(pil_img)
    img_width, img_height = pil_img.size

    content_type = img_response.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()
    if content_type not in ('image/jpeg', 'image/png', 'image/webp', 'image/tiff'):
        content_type = 'image/jpeg'

    client = OpenAI(
        api_key=os.getenv("GOOGLE_API_KEY"),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )

    user_content = [
        {"type": "text", "text": "Analyze this document image and return the OCR results as a JSON array as described."},
        {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{image_base64}"}}
    ]
    system_prompt = OCR_FULL_PROMPT if generate_text else OCR_LAYOUT_PROMPT

    return client, user_content, system_prompt, img_width, img_height


def get_gemini_ocr_output(image_url, model, generate_text=True, log_context=None):
    """Call Gemini (non-streaming) and return the full list of annotation dicts."""
    try:
        client, user_content, system_prompt, img_width, img_height = _prepare_gemini_request(
            image_url, model, generate_text
        )

        response = client.chat.completions.create(
            model=model.replace("google-ocr/", ""),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            response_format={"type": "json_object"} if "gemini-2" in model else None,
        )

        raw = response.choices[0].message.content.strip()

        print(f"\n=== GEMINI OCR RAW RESPONSE (img {img_width}x{img_height}) ===")
        print(raw[:3000])
        print("=== END GEMINI OCR RESPONSE ===\n")

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            for key in ('regions', 'result', 'ocr_result', 'annotations', 'items'):
                if key in parsed and isinstance(parsed[key], list):
                    parsed = parsed[key]
                    break
            else:
                for v in parsed.values():
                    if isinstance(v, list):
                        parsed = v
                        break
                else:
                    parsed = []

        return [_process_ocr_item(item, img_width, img_height, i, generate_text) for i, item in enumerate(parsed)]

    except Exception as e:
        log_and_raise(e, model_code=model, provider='google',
                      custom_message=f"Gemini OCR error: {str(e)}", log_context=log_context)


def stream_gemini_ocr_output(image_url, model, generate_text=True, log_context=None):
    """Generator — yields individual annotation dicts as they're parsed from Gemini's streaming response."""
    try:
        client, user_content, system_prompt, img_width, img_height = _prepare_gemini_request(
            image_url, model, generate_text
        )

        stream = client.chat.completions.create(
            model=model.replace("google-ocr/", ""),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            stream=True,
        )

        # Incrementally parse JSON objects from the token stream.
        # Strategy: track brace depth (ignoring braces inside strings).
        # Each time depth falls back to 0, we have a complete top-level object.
        buf = ''
        depth = 0
        obj_start = None
        in_string = False
        escape_next = False
        item_counter = 0

        for chunk in stream:
            if not chunk.choices:
                continue
            token = chunk.choices[0].delta.content or ''
            for ch in token:
                buf += ch

                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\' and in_string:
                    escape_next = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue

                if ch == '{':
                    depth += 1
                    if depth == 1:
                        obj_start = len(buf) - 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0 and obj_start is not None:
                        obj_str = buf[obj_start:]
                        try:
                            item = json.loads(obj_str)
                            yield _process_ocr_item(item, img_width, img_height, item_counter, generate_text)
                            item_counter += 1
                        except Exception:
                            pass
                        obj_start = None
                        buf = ''  # free memory; next obj_start will be relative to new buf

    except Exception as e:
        log_and_raise(e, model_code=model, provider='google',
                      custom_message=f"Gemini OCR streaming error: {str(e)}", log_context=log_context)


REGION_TEXT_PROMPT = """Transcribe all text visible in this image exactly as it appears. Return only the raw text, no explanation. Preserve line breaks using \\n. If there is no text, return an empty string."""


def extract_region_text(image_url, box, model="gemini-2.0-flash", log_context=None):
    """Crop a region from the document image and extract its text via Gemini.
    box: [x1, y1, x2, y2] in natural pixel coordinates.
    Returns the extracted text string.
    """
    try:
        img_response = requests.get(image_url, timeout=60)
        img_response.raise_for_status()
        image_data = img_response.content

        from PIL import ImageOps
        pil_img = PILImage.open(io.BytesIO(image_data))
        pil_img = ImageOps.exif_transpose(pil_img)

        x1, y1, x2, y2 = [int(v) for v in box]
        cropped = pil_img.crop((x1, y1, x2, y2))

        buf = io.BytesIO()
        cropped.save(buf, format='PNG')
        crop_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        client = OpenAI(
            api_key=os.getenv("GOOGLE_API_KEY"),
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )

        response = client.chat.completions.create(
            model=model.replace("google-ocr/", ""),
            messages=[
                {"role": "system", "content": REGION_TEXT_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": "Transcribe the text in this region."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{crop_b64}"}},
                ]},
            ],
            temperature=0.1,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        log_and_raise(e, model_code=model, provider='google',
                      custom_message=f"Region text extraction error: {str(e)}", log_context=log_context)


def get_ocr_output(image_url, model="google-ocr/gemini-2.5-pro", generate_text=True, log_context=None):
    """Non-streaming: returns the full list of annotations."""
    if model.startswith("google-ocr/") or model.startswith("gemini"):
        return get_gemini_ocr_output(image_url, model, generate_text=generate_text, log_context=log_context)
    return get_gemini_ocr_output(image_url, model, generate_text=generate_text, log_context=log_context)


def stream_ocr_output(image_url, model="google-ocr/gemini-2.5-pro", generate_text=True, log_context=None):
    """Streaming: generator that yields individual annotation dicts."""
    if model.startswith("google-ocr/") or model.startswith("gemini"):
        return stream_gemini_ocr_output(image_url, model, generate_text=generate_text, log_context=log_context)
    return stream_gemini_ocr_output(image_url, model, generate_text=generate_text, log_context=log_context)
