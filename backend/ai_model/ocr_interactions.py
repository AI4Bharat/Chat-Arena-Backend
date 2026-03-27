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
OCR_LAYOUT_PROMPT = """You are a document layout analysis engine. Your task is to detect all content regions in a document image and classify them accurately.

The document may be: machine-printed, typewritten, handwritten, scanned, photographed, a historical manuscript, a form, a table-heavy report, a receipt, a chart, a newspaper, a legal document, or any other format. Handle all of these robustly.

Return ONLY a valid JSON array (no markdown, no explanation) where each element has:
- "id": a unique string identifier (e.g. "r1", "r2", ...)
- "box_2d": [ymin, xmin, ymax, xmax] — values in [0, 1000] where (0,0) is top-left and (1000,1000) is bottom-right
- "type": one of "title", "heading", "paragraph", "table", "figure", "caption", "list", "other"

Rules:
- box_2d values must be integers in [0, 1000]; ymin < ymax, xmin < xmax
- Each box must FULLY encompass all content belonging to that region — do not clip rows or columns of a table, do not split a paragraph mid-sentence
- COMPLETENESS IS MANDATORY: every visible piece of content on the page must be covered by exactly one region — nothing may be skipped, even on dense or multi-table pages
- A table is any grid of data with rows and columns, even if borders are faint, partial, or absent (whitespace-aligned columns still count); even a simple 2-column key/value grid is a table
- EACH table on the page gets its own separate region — never group multiple tables into one
- A table caption or label (e.g. "Table 1", "Table 2: ...") is a SEPARATE region from its table — never merge them
- Detect every distinct content block in natural reading order (top-to-bottom, left-to-right; for multi-column layouts follow column order)
- Do NOT extract or return any text content"""

# Full OCR prompt — detects regions and transcribes text within each region.
OCR_FULL_PROMPT = """You are a document layout analysis and OCR engine. Your task is to detect all content regions in a document image, classify them, and transcribe the text within each region.

The document may be: machine-printed, typewritten, handwritten (cursive or print), scanned at any quality, photographed at an angle, a historical transcript, a form, a receipt, a table-heavy report, a newspaper, a legal document, or any other format. Apply robust OCR regardless of font, language script, or document condition.

Return ONLY a valid JSON array (no markdown, no explanation) where each element has:
- "id": a unique string identifier (e.g. "r1", "r2", ...)
- "box_2d": [ymin, xmin, ymax, xmax] — values in [0, 1000] where (0,0) is top-left and (1000,1000) is bottom-right
- "type": one of "title", "heading", "paragraph", "table", "figure", "caption", "list", "other"
- "text": the transcribed text content of this region (empty string "" for figures/images with no readable text)

General rules:
- box_2d values must be integers in [0, 1000]; ymin < ymax, xmin < xmax
- Each box must FULLY encompass all content belonging to that region
- COMPLETENESS IS MANDATORY: every visible piece of content on the page must be covered by exactly one region — nothing may be skipped, even if the page is dense or has many tables
- Detect every distinct content block in natural reading order (top-to-bottom, left-to-right; for multi-column layouts follow column order)
- Transcribe text exactly as it appears — preserve original spelling, punctuation, capitalisation, and abbreviations
- For unclear or degraded text, transcribe your best reading; never skip a region because it is difficult
- For figure/image-only regions with no readable text, set "text" to ""

Table rules (type = "table"):
- Classify any grid of data as a table — borders may be ruled lines, dotted lines, whitespace alignment, or absent entirely; even a simple 2-column key/value grid is a table
- EACH table on the page gets its own separate region — never group multiple tables into a single region
- A table caption or label (e.g. "Table 1", "Table 2: example of footnotes") is a SEPARATE region of type "caption" or "heading" — never merge a caption into its table's bounding box
- The bounding box must cover the ENTIRE table grid including all header rows, data rows, and footer rows, but must NOT include the caption/label above or footnotes below (those are separate regions)
- Represent content as TSV (tab-separated values): columns separated by \t, rows separated by \n
- Multi-level / stacked headers: flatten into a single header row by combining parent and child labels with a space (e.g. a "Results" group spanning "Accuracy" and "Time to complete" → header cells become "Results Accuracy" and "Results Time to complete")
- Merged / spanned cells: repeat the cell value in each logical column it spans
- Preserve the exact data values in each cell; do not paraphrase or summarise
- Row order must match the visual top-to-bottom order of the table"""


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


REGION_TEXT_PROMPT = """You are an OCR engine for a document region crop. Transcribe all readable text in this image exactly as it appears.

Rules:
- Return ONLY the transcribed text — no explanations, labels, or markdown
- Preserve original spelling, punctuation, capitalisation, and abbreviations
- Preserve line breaks using \\n
- For tables or grid data: use TSV format — columns separated by \\t, rows separated by \\n; flatten multi-level headers by combining parent + child labels (e.g. "Results Accuracy"), repeat merged cell values across spanned columns
- Handle any input: machine-printed, typewritten, handwritten, scanned, degraded, or historical text
- If there is no readable text, return an empty string"""


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
