"""Answer-sheet evaluation: a vision LLM marks a student's whole answer sheet.

All pages of the sheet go to the model in one request, so an answer that runs onto
the next page is judged as one answer. The result is a flat list streamed one object
at a time:

  answer   — one per question: the question label, an overall category, marks out of
             ``max_marks``, an optional per-criterion marks breakdown, an overall comment
             and ``parts``: one or more boxes, each on a page. An answer that continues
             across pages has one part per page (many boxes -> one question).
  finding  — zero or more per answer: a box on one page around a specific step / line /
             word, a category and a comment. ``answer_id`` links it to its answer.

Pages are numbered from 1. Boxes are returned in natural pixel coordinates of their page.

Vision models (Gemini, and Gemma 4 on Sarvam) receive the page images and answer with
boxes; text-only models (DeepSeek V4 Flash on Sarvam) receive an OCR transcript and answer
with line ids, which are turned back into boxes. When Bodhan's document OCR (indic-ocr) is
configured, Gemma gets both: each page image followed by that page's OCR blocks, and it
locates answers by block id, so boxes come from the OCR layout ("hybrid" mode).

A teacher can also send feedback ("Q2: units are wrong, deduct a mark") and have the
model revise one answer, the answers on one page, or the whole sheet
(``stream_reevaluation``). The model then returns a short ``reply`` to the teacher
followed by the revised answers, which ``merge_revision`` folds back into the list
(an answer the model leaves out is kept as it was).
"""
import base64
import io
import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import requests
from openai import OpenAI
from PIL import Image as PILImage, ImageOps

from ai_model.error_logging import log_and_raise

logger = logging.getLogger(__name__)

GEMINI_PREFIX = "google-eval/"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

DEFAULT_MAX_MARKS = 10
MAX_MARKS_LIMIT = 100
MAX_DOCUMENT_PAGES = 20
MAX_REFERENCE_PAGES = 6
MAX_INSTRUCTIONS_CHARS = 4000
MAX_PARTS_PER_ANSWER = 10

CATEGORIES = (
    "correct",
    "minor_mistake",
    "major_mistake",
    "incomplete",
    "illegible",
    "unattempted",
)


class EvaluationError(Exception):
    """A configuration or input problem whose message is safe to show to the user."""


_CATEGORY_ALIASES = {
    "right": "correct",
    "fully_correct": "correct",
    "minor": "minor_mistake",
    "minor_error": "minor_mistake",
    "partially_correct": "minor_mistake",
    "major": "major_mistake",
    "major_error": "major_mistake",
    "incorrect": "major_mistake",
    "wrong": "major_mistake",
    "conceptual_error": "major_mistake",
    "partial": "incomplete",
    "missing": "incomplete",
    "missing_step": "incomplete",
    "unreadable": "illegible",
    "not_attempted": "unattempted",
    "blank": "unattempted",
}

# The marking guidance (who the examiner is, how to mark and comment) is a plain-text
# file a teacher or developer can rewrite; EVAL_SYSTEM_PROMPT_FILE points at a replacement.
# The output contract below it is appended by code, so a custom prompt cannot break the
# JSON the app parses. "{max_marks}" in the guidance is replaced with the session's value.
GUIDANCE_FILE = Path(__file__).resolve().parent / "prompts" / "evaluation_system_prompt.md"

_CATEGORY_RULES = """Categories:
- "correct": correct and complete
- "minor_mistake": a small slip that does not show a misunderstanding (arithmetic slip, units, spelling, notation)
- "major_mistake": an error that shows a misunderstanding or makes the answer wrong (wrong method, concept or final answer)
- "incomplete": missing steps, parts or justification
- "illegible": cannot be read reliably
- "unattempted": the question appears on the sheet but has no answer"""

_ANSWER_FIELDS = """- "kind": "answer"
- "id": unique id such as "q1", "q2"
- "question": the question label as written on the sheet (e.g. "Q1", "13", "2(b)"); infer it from order if unlabeled
- "question_text": one short line saying what the question asks ("" if unknown)
{location}
- "category": overall verdict, one of the categories below
- "marks_awarded": marks out of {marks_of}, in steps of 0.5
- "max_marks": {max_marks_value}
- "marks_breakdown": 1 to 4 criteria as [{{"criterion": "...", "awarded": n, "max": n}}]; the "max" values sum to {marks_of} and the "awarded" values sum to marks_awarded
- "comment": 1 to 3 sentences justifying the marks for the whole answer: what is right, what is wrong, and why
- "findings": this answer's "finding" objects (below): one for every place where it lost marks; [] for a fully correct answer"""

_FINDING_FIELDS = """- "kind": "finding"
- "id": unique id such as "q1-f1"
- "answer_id": the id of the answer it belongs to
{location}
- "category": one of the categories below
- "comment": what exactly is wrong (quote the student's text) and what the correct version is, or why the step is notably good
- "marks_impact": marks lost because of this finding as a negative number (e.g. -1), or 0"""

_OUTPUT_HEAD = """

---
OUTPUT FORMAT (required: the app cannot read anything else)
Return ONLY a valid JSON array (no markdown, no explanation) of "answer" objects, one per question in
the order of the sheet; each answer carries its own "finding" objects in its "findings" list.
Each array element is the answer object itself, starting with "kind"; never wrap it as {{"answer": {{...}}}}.
Each numbered question is ONE answer with its own location: never put several numbered questions (for
example 13, 14 and 15) in one answer, even when they share a section heading.
The comment, category, marks and findings of an answer must agree; comments state final conclusions only.
Every answer that loses marks has at least one finding at the place where they were lost, and its
findings' "marks_impact" values add up to the marks it lost.

{marks_rules}

"answer" object — exactly one per question, even when the answer spans several pages:
{answer}

"finding" object, inside its answer's "findings" — one or more for every answer that loses marks, each at one
specific mistake (none for a fully correct answer, though a notably good step may get one):
{finding}

{categories}

"""

IMAGE_INPUT = """

---
INPUT
You receive, in this order: optionally REFERENCE pages (the question paper and/or the answer key /
marking scheme); optionally TEACHER INSTRUCTIONS; then the STUDENT ANSWER SHEET pages, each
labelled with its page number. Evaluate every answer on them."""

IMAGE_LOCATION_ANSWER = """- "parts": the boxes that together make up the student's COMPLETE answer, including working and diagrams, as
  [{{"page": n, "box_2d": [ymin, xmin, ymax, xmax]}}]. One part per page the answer appears on, in reading order.
  An answer that continues onto the next page (often without repeating its label) gets a second part on that page —
  never a new answer."""
IMAGE_LOCATION_FINDING = """- "page": the page the finding is on
- "box_2d": [ymin, xmin, ymax, xmax] tightly around the specific step, line, word or diagram part"""
IMAGE_RULES = """Rules:
- "page" is the student answer sheet page number shown above each page image. box_2d values are integers in [0, 1000] where (0, 0) is the top-left and (1000, 1000) the bottom-right of THAT page; ymin < ymax and xmin < xmax. Never give coordinates for reference pages.
- A box_2d is exactly ONE box: four integers, never a list of boxes. Each part has exactly one "page" and one "box_2d"; when an answer has several separate pieces on one page, give one box around all of them.
- If the pages contain no answers, return [].

Example of the shape (the values are illustrative):
[{"kind": "answer", "id": "q13", "question": "13", "question_text": "What are emotions?", "parts": [{"page": 3, "box_2d": [138, 125, 195, 770]}], "category": "minor_mistake", "marks_awarded": 0.5, "max_marks": 1, "marks_breakdown": [{"criterion": "Definition", "awarded": 0.5, "max": 1}], "comment": "Names feelings such as happiness but does not say what an emotion is.", "findings": [{"kind": "finding", "id": "q13-f1", "answer_id": "q13", "page": 3, "box_2d": [140, 130, 168, 520], "category": "incomplete", "comment": "Lists examples only; an emotion is a strong feeling such as joy, fear or anger.", "marks_impact": -0.5}]},
 {"kind": "answer", "id": "q17", "question": "17", "question_text": "Penalties for fouls in the 'D' area in hockey", "parts": [{"page": 3, "box_2d": [449, 140, 505, 900]}], "category": "correct", "marks_awarded": 2, "max_marks": 2, "marks_breakdown": [{"criterion": "Penalty named", "awarded": 1, "max": 1}, {"criterion": "Explanation", "awarded": 1, "max": 1}], "comment": "Correctly says a penalty corner is given for a defender's foul inside the D.", "findings": []}]"""

TEXT_INPUT = """

---
INPUT
You receive, in this order: optionally the REFERENCE material (the question paper and/or the answer
key / marking scheme) as text; optionally TEACHER INSTRUCTIONS; then the STUDENT ANSWER SHEET as an
OCR transcript of every page. Each transcript line starts with its id in square brackets: [3.12] is
page 3, line 12. OCR can misread handwriting (for example "O" for "0", "l" for "1", "x" for a
multiplication sign); read past obvious OCR errors using the context, but never invent content
the student did not write. Evaluate every answer in the transcript."""

TEXT_LOCATION_ANSWER = """- "lines": the ids of ALL the transcript lines that make up the student's complete answer to this question,
  including working, on every page it continues onto, e.g. ["2.20", "2.21", "3.1", "3.2"]. A run of
  consecutive lines on one page may be written as a range, e.g. "3.1-3.38". An answer that continues
  onto the next page (often without repeating its label) keeps the same answer — never a new answer."""
TEXT_LOCATION_FINDING = """- "lines": the id(s) of the specific line(s) the finding is about, usually just one, e.g. ["3.9"]"""
TEXT_RULES = """Rules:
- Use only line ids that appear in the transcript. Lines that are not part of any answer (names, section headings, page numbers) belong to no answer.
- If the transcript contains no answers, return [].

Example of the shape (the values are illustrative):
[{"kind": "answer", "id": "q13", "question": "13", "question_text": "What are emotions?", "lines": ["3.4-3.5"], "category": "minor_mistake", "marks_awarded": 0.5, "max_marks": 1, "marks_breakdown": [{"criterion": "Definition", "awarded": 0.5, "max": 1}], "comment": "Names feelings such as happiness but does not say what an emotion is.", "findings": [{"kind": "finding", "id": "q13-f1", "answer_id": "q13", "lines": ["3.4"], "category": "incomplete", "comment": "Lists examples only; an emotion is a strong feeling such as joy, fear or anger.", "marks_impact": -0.5}]},
 {"kind": "answer", "id": "q17", "question": "17", "question_text": "Penalties for fouls in the 'D' area in hockey", "lines": ["3.15-3.16"], "category": "correct", "marks_awarded": 2, "max_marks": 2, "marks_breakdown": [{"criterion": "Penalty named", "awarded": 1, "max": 1}, {"criterion": "Explanation", "awarded": 1, "max": 1}], "comment": "Correctly says a penalty corner is given for a defender's foul inside the D.", "findings": []}]"""


HYBRID_INPUT = """

---
INPUT
You receive, in this order: optionally the REFERENCE material (the question paper and/or the answer
key / marking scheme) as page images, each followed by its OCR text; optionally TEACHER INSTRUCTIONS;
then the STUDENT ANSWER SHEET, page by page: each page image, followed by the OCR BLOCKS of that page.

How to use the OCR blocks
- A dedicated OCR model has split every page into layout blocks (paragraphs, lists, tables, headings,
  pictures) and read their text. Each block starts with its id and type: "[3.4] (Text)" is page 3,
  block 4, in reading order. Pictures and drawings are blocks with no text.
- Use the OCR text to read the page quickly and completely, and to quote the student exactly, in the
  student's own script. It is far better than reading small handwriting from the image alone.
- The page image is the truth. OCR can misread handwriting (similar-looking letters and digits, "x" vs
  "×", decimal points, fractions), miss ticks, circles, crossings-out and arrows, merge two answers
  into one block or split one answer across blocks. Before marking anything as wrong, check it on the
  image; when the image and the OCR disagree, follow the image and quote what is really written.
- Judge diagrams, graphs, drawings, matchings drawn with lines, and circled or ticked options from the
  image.
- Printed text in a block (the question itself on a worksheet) is not the student's work: mark only
  what the student wrote.
- Locate everything with block ids, never by estimating coordinates: the app draws the boxes from the
  OCR blocks, which are pixel-exact."""

HYBRID_LOCATION_ANSWER = """- "blocks": the ids of ALL the OCR blocks that make up the student's complete answer to this question,
  including working and diagrams, on every page it continues onto, e.g. ["2.7", "2.8", "3.1"]. A run of
  consecutive blocks may be written as a range, e.g. "3.1-3.4". An answer that continues onto the next
  page (often without repeating its label) keeps the same answer — never a new answer.
- "parts": only for a piece of the answer that has NO OCR block (the OCR missed it), or when one block
  holds several answers: [{{"page": n, "box_2d": [ymin, xmin, ymax, xmax]}}] around this answer's own piece."""
HYBRID_LOCATION_FINDING = """- "blocks": the id of the OCR block the finding is in, e.g. ["3.4"]
- "box_2d": optional, [ymin, xmin, ymax, xmax] tightly around the exact word, step or line inside that
  block, when the block is much larger than what the finding is about"""
HYBRID_RULES = """Rules:
- Use only block ids that appear in the OCR blocks. Blocks that are not part of any answer (names, headings, printed instructions, page numbers, teacher's marks) belong to no answer.
- box_2d values are integers in [0, 1000] where (0, 0) is the top-left and (1000, 1000) the bottom-right of that student page; ymin < ymax and xmin < xmax. A box_2d is exactly ONE box of four integers.
- If the pages contain no answers, return [].

Example of the shape (the values are illustrative):
[{"kind": "answer", "id": "q13", "question": "13", "question_text": "What are emotions?", "blocks": ["3.3"], "category": "minor_mistake", "marks_awarded": 0.5, "max_marks": 1, "marks_breakdown": [{"criterion": "Definition", "awarded": 0.5, "max": 1}], "comment": "Names feelings such as happiness but does not say what an emotion is.", "findings": [{"kind": "finding", "id": "q13-f1", "answer_id": "q13", "blocks": ["3.3"], "box_2d": [140, 130, 168, 520], "category": "incomplete", "comment": "Lists examples only; an emotion is a strong feeling such as joy, fear or anger.", "marks_impact": -0.5}]},
 {"kind": "answer", "id": "q17", "question": "17", "question_text": "Penalties for fouls in the 'D' area in hockey", "blocks": ["3.12"], "category": "correct", "marks_awarded": 2, "max_marks": 2, "marks_breakdown": [{"criterion": "Penalty named", "awarded": 1, "max": 1}, {"criterion": "Explanation", "awarded": 1, "max": 1}], "comment": "Correctly says a penalty corner is given for a defender's foul inside the D.", "findings": []}]"""


# How marks are set. The teacher can fix the marks per question; left blank (None), each question's
# maximum is read from the question paper (or the answer sheet when it carries the questions).
MARKS_FROM_PAPER = """MARKS
Take each question's maximum marks from the question paper, or from the answer sheet itself when the
questions are printed on it: a mark printed beside the question ("[2]", "(3 marks)", "2M"), or a section
scheme beside its heading such as "4X1=4" (four questions of 1 mark each) or "4X3=12" (four questions of
3 marks each). Follow the answer key's split of marks when one is given. When nothing on the paper gives a
question's marks, use {fallback}. Put that maximum in "max_marks" and mark the answer out of it."""

MARKS_FIXED = """MARKS
Every question is marked out of {marks}, as set by the teacher, whatever marks the paper prints. When the
paper gives a question a different number of marks, mark it on the paper's scheme and scale the result to
{marks}."""


def marks_setting(value):
    """The teacher's marks per question as a number, or None to read them from the paper."""
    if value in (None, "") or (isinstance(value, str) and not value.strip()):
        return None
    marks = _number(value)
    return clamp_max_marks(marks) if marks and marks > 0 else None


def load_guidance(max_marks=DEFAULT_MAX_MARKS):
    """The examiner guidance: EVAL_SYSTEM_PROMPT_FILE if set, else the bundled prompt.

    "{max_marks}" is replaced with the marks per question, or, when they come from the
    paper (max_marks None), with words pointing at the MARKS rules."""
    path = Path(os.getenv("EVAL_SYSTEM_PROMPT_FILE") or GUIDANCE_FILE)
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as e:
        raise EvaluationError(f"Cannot read the evaluation system prompt at {path}: {e.strerror}.")
    if max_marks is None:
        text = text.replace("out of {max_marks} marks", "out of the marks the question paper gives it (see MARKS below)")
        return text.replace("{max_marks}", "its maximum marks")
    return text.replace("{max_marks}", str(_format_marks(max_marks)))


_PROMPT_MODES = {
    # mode: (input, answer location, finding location, rules)
    "image": (IMAGE_INPUT, IMAGE_LOCATION_ANSWER, IMAGE_LOCATION_FINDING, IMAGE_RULES),
    "text": (TEXT_INPUT, TEXT_LOCATION_ANSWER, TEXT_LOCATION_FINDING, TEXT_RULES),
    "hybrid": (HYBRID_INPUT, HYBRID_LOCATION_ANSWER, HYBRID_LOCATION_FINDING, HYBRID_RULES),
}


# The last line of every evaluation request: weaker models (Gemma 4) follow the end of the
# request most closely, and otherwise group numbered items into one answer.
EVALUATE_REQUEST = ("Evaluate this answer sheet and return the JSON array described: one answer for each numbered "
                    "question, each with a finding for every place where it lost marks.")


def build_evaluation_prompt(max_marks=None, mode="image"):
    """System prompt: the guidance, then how the input looks and the output contract.

    ``mode`` is "image" for vision models that get page images and answer with boxes,
    "text" for text-only models that get an OCR transcript and answer with line ids, or
    "hybrid" for vision models that get page images AND OCR blocks and answer with block ids.
    ``max_marks`` None means each question's maximum comes from the paper.
    """
    source, answer_at, finding_at, rules = _PROMPT_MODES[mode]
    if max_marks is None:
        marks_of, max_value = "max_marks", "this question's maximum marks, from the paper (see MARKS)"
        marks_rules = MARKS_FROM_PAPER.format(fallback=_format_marks(DEFAULT_MAX_MARKS))
    else:
        marks_of = max_value = _format_marks(max_marks)
        marks_rules = MARKS_FIXED.format(marks=marks_of)
    answer = _ANSWER_FIELDS.format(location=answer_at, marks_of=marks_of, max_marks_value=max_value)
    finding = _FINDING_FIELDS.format(location=finding_at)
    return (load_guidance(max_marks)
            + source
            + _OUTPUT_HEAD.format(answer=answer.replace("{{", "{").replace("}}", "}"),
                                  finding=finding, categories=_CATEGORY_RULES, marks_rules=marks_rules)
            + rules)


def clamp_max_marks(value):
    try:
        marks = float(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_MARKS
    if not math.isfinite(marks) or marks <= 0:
        return DEFAULT_MAX_MARKS
    return _round_half(min(marks, MAX_MARKS_LIMIT))


def normalize_category(value, default="minor_mistake"):
    if not isinstance(value, str):
        return default
    key = re.sub(r"[\s\-]+", "_", value.strip().lower())
    if key in CATEGORIES:
        return key
    return _CATEGORY_ALIASES.get(key, default)


def _round_half(value):
    return math.floor(value * 2 + 0.5) / 2


def _format_marks(value):
    return int(value) if float(value).is_integer() else value


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _page_number(value):
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def _text(value, limit):
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _to_pixel_box(raw_box, img_width, img_height):
    """[ymin, xmin, ymax, xmax] in 0-1000 → [x1, y1, x2, y2] in natural pixels, or None."""
    if not isinstance(raw_box, (list, tuple)) or len(raw_box) != 4:
        return None
    values = [_number(v) for v in raw_box]
    if any(v is None for v in values):
        return None
    ymin, xmin, ymax, xmax = [min(max(v, 0.0), 1000.0) for v in values]
    ymin, ymax = sorted((ymin, ymax))
    xmin, xmax = sorted((xmin, xmax))
    box = [
        int(round(xmin * img_width / 1000)),
        int(round(ymin * img_height / 1000)),
        int(round(xmax * img_width / 1000)),
        int(round(ymax * img_height / 1000)),
    ]
    if box[2] - box[0] < 2 or box[3] - box[1] < 2:
        return None
    return box


def _to_box_2d(box, img_width, img_height):
    x1, y1, x2, y2 = box
    return [round(y1 * 1000 / img_height), round(x1 * 1000 / img_width),
            round(y2 * 1000 / img_height), round(x2 * 1000 / img_width)]


def answer_pages(item):
    """Pages (1-based) an answer has boxes on."""
    return sorted({p.get("page") for p in item.get("parts") or [] if p.get("page")})


class EvaluationNormalizer:
    """Turns raw model objects into stable annotation dicts, one at a time.

    ``page_sizes`` maps page number -> (width, height) in pixels. Keeps ids unique,
    resolves each finding's ``answer_id`` to the final id of its answer (falling back to
    the most recent answer), drops parts on unknown pages, and clamps marks.
    """

    def __init__(self, page_sizes, max_marks=DEFAULT_MAX_MARKS, reserved_ids=()):
        """``max_marks`` fixes every question's maximum; None takes each answer's own max_marks
        (read from the paper by the model), falling back to its breakdown's total, then 10."""
        self.page_sizes = {int(k): v for k, v in page_sizes.items()}
        self.fixed_max = None if max_marks is None else clamp_max_marks(max_marks)
        self.max_marks = self.fixed_max or DEFAULT_MAX_MARKS
        self._answer_max = {}  # final answer id -> its maximum marks
        self._used_ids = set(reserved_ids)  # ids already used elsewhere in the evaluation
        self._answer_ids = {}  # model-given id -> final id
        self._answer_pages = {}  # final answer id -> first page with a part
        self._last_answer_id = None
        self._answers = 0
        self._findings = 0

    def _unique_id(self, raw_id, fallback):
        base = re.sub(r"[^A-Za-z0-9_-]", "", str(raw_id or ""))[:40] or fallback
        candidate, n = base, 2
        while candidate in self._used_ids:
            candidate, n = f"{base}-{n}", n + 1
        self._used_ids.add(candidate)
        return candidate

    def _is_finding(self, raw):
        kind = str(raw.get("kind") or raw.get("type") or "").strip().lower()
        if kind in ("finding", "issue", "annotation", "comment"):
            return True
        if kind == "answer":
            return False
        return "answer_id" in raw and "marks_awarded" not in raw

    def _marks(self, value, limit):
        number = _number(value)
        if number is None:
            return None
        return _round_half(min(max(number, 0.0), limit))

    def _answer_maximum(self, raw):
        if self.fixed_max:
            return self.fixed_max
        stated = _number(raw.get("max_marks"))
        if stated and stated > 0:
            return clamp_max_marks(stated)
        rows = raw.get("marks_breakdown") if isinstance(raw.get("marks_breakdown"), list) else []
        total = sum(_number(r.get("max")) or 0 for r in rows if isinstance(r, dict))
        return clamp_max_marks(total) if total > 0 else DEFAULT_MAX_MARKS

    def _breakdown(self, rows, limit):
        if not isinstance(rows, list):
            return []
        cleaned = []
        for row in rows[:6]:
            if not isinstance(row, dict):
                continue
            row_max = _number(row.get("max"))
            if row_max is None or row_max <= 0:
                continue
            row_max = _round_half(min(row_max, limit))
            cleaned.append({
                "criterion": _text(row.get("criterion") or row.get("name"), 60) or "Criterion",
                "awarded": self._marks(row.get("awarded"), row_max) or 0,
                "max": row_max,
            })
        return cleaned

    def _scaled(self, breakdown, awarded, maximum):
        """Scale a marks distribution on another scale (e.g. 2.5 of 2.5, or 3 x 3.5) to the
        answer's maximum, as the contract requires; marks_awarded too when it is the unscaled sum."""
        total_max = sum(r["max"] for r in breakdown)
        if not breakdown or total_max <= 0 or abs(total_max - maximum) < 0.01:
            return breakdown, awarded
        factor = maximum / total_max
        raw_sum = sum(r["awarded"] for r in breakdown)
        scaled = [{**r, "awarded": round(r["awarded"] * factor, 2), "max": round(r["max"] * factor, 2)} for r in breakdown]
        if awarded is None or abs(awarded - raw_sum) < 0.01:
            awarded = raw_sum * factor
        return scaled, awarded

    def _box(self, raw_box, page):
        """One pixel box from a box_2d, or from a list of them (their union), or None."""
        size = self.page_sizes.get(page)
        if not size:
            return None
        if isinstance(raw_box, (list, tuple)) and raw_box and all(isinstance(b, (list, tuple)) for b in raw_box):
            boxes = [b for b in (_to_pixel_box(b, *size) for b in raw_box) if b]
            return [min(b[0] for b in boxes), min(b[1] for b in boxes),
                    max(b[2] for b in boxes), max(b[3] for b in boxes)] if boxes else None
        return _to_pixel_box(raw_box, *size)

    def _parts(self, raw, answer_id):
        raw_parts = raw.get("parts")
        if not isinstance(raw_parts, list):  # a single-box answer, as {"page", "box_2d"}
            raw_parts = [{"page": raw.get("page", 1), "box_2d": raw.get("box_2d") or raw.get("box")}]
        # A part that repeats its keys ({"page": 2, "box_2d": ..., "page": 3, ...}) is several parts.
        pieces = [piece for part in raw_parts if isinstance(part, dict)
                  for piece in [part, *part.get(REPEATED_KEYS, [])]]
        parts = []
        for part in pieces[:MAX_PARTS_PER_ANSWER]:
            page = _page_number(part.get("page"))
            box = self._box(part.get("box_2d") or part.get("box"), page)
            if box:
                parts.append({"id": self._unique_id(f"{answer_id}-p{len(parts) + 1}", "p"), "page": page, "box": box})
        return parts

    def add(self, raw):
        if not isinstance(raw, dict):
            return None

        if self._is_finding(raw):
            self._findings += 1
            answer_id = self._answer_ids.get(str(raw.get("answer_id") or "")) or self._last_answer_id
            page = _page_number(raw.get("page")) or self._answer_pages.get(answer_id) or 1
            impact = _number(raw.get("marks_impact"))
            limit = self._answer_max.get(answer_id, self.max_marks)
            lost = min(_round_half(abs(impact)), limit) if impact else 0
            return {
                "id": self._unique_id(raw.get("id"), f"f{self._findings}"),
                "kind": "finding",
                "answer_id": answer_id,
                "page": page,
                "box": self._box(raw.get("box_2d") or raw.get("box"), page),
                "category": normalize_category(raw.get("category")),
                "comment": _text(raw.get("comment"), 2000),
                "marks_impact": -lost if lost else 0,
            }

        self._answers += 1
        answer_id = self._unique_id(raw.get("id"), f"q{self._answers}")
        if raw.get("id") is not None:
            self._answer_ids[str(raw.get("id"))] = answer_id
        self._last_answer_id = answer_id
        parts = self._parts(raw, answer_id)
        if parts:
            self._answer_pages[answer_id] = parts[0]["page"]

        maximum = self._answer_maximum(raw)
        self._answer_max[answer_id] = maximum
        breakdown, awarded = self._scaled(self._breakdown(raw.get("marks_breakdown"), maximum),
                                          _number(raw.get("marks_awarded")), maximum)
        awarded = self._marks(awarded, maximum)
        if awarded is None:
            awarded = self._marks(sum(r["awarded"] for r in breakdown), maximum) if breakdown else 0
        return {
            "id": answer_id,
            "kind": "answer",
            "question": _text(raw.get("question"), 40) or f"Q{self._answers}",
            "question_text": _text(raw.get("question_text"), 300),
            "parts": parts,
            "category": normalize_category(raw.get("category")),
            "marks_awarded": awarded,
            "max_marks": maximum,
            "marks_breakdown": breakdown,
            "comment": _text(raw.get("comment"), 2000),
        }


# Where _keep_repeated_keys puts the later groups of a JSON object that repeats its keys.
REPEATED_KEYS = "__repeated__"
_WRAPPER_KINDS = ("answer", "finding", "reply")


def _keep_repeated_keys(pairs):
    """json object_pairs_hook: a key that repeats starts a new group instead of overwriting.

    Some models write two parts as one object, {"page": 2, "box_2d": [..], "page": 3, "box_2d": [..]};
    json.loads would keep only page 3.
    """
    groups = [{}]
    for key, value in pairs:
        if key in groups[-1]:
            groups.append({})
        groups[-1][key] = value
    first = groups[0]
    if len(groups) > 1:
        first[REPEATED_KEYS] = groups[1:]
    return first


def iter_json_objects(chunks):
    """Yield each complete top-level JSON object found in a stream of text chunks.

    Tolerates a leading ``[``, markdown fences and commas between objects. If the
    model wraps its array in an object (``{"annotations": [...]}``), the wrapper's
    list items are yielded instead.
    """
    buf = []
    depth = 0
    in_string = False
    escape = False
    for chunk in chunks:
        for ch in chunk or "":
            if depth == 0 and ch != "{":
                continue
            buf.append(ch)
            if escape:
                escape = False
            elif in_string:
                if ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            elif ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    text, buf = "".join(buf), []
                    try:
                        obj = json.loads(text, object_pairs_hook=_keep_repeated_keys)
                    except ValueError:
                        logger.warning("Skipping unparseable evaluation object: %.200s", text)
                        continue
                    yield from _unwrap(obj)


def _unwrap(obj):
    if not isinstance(obj, dict):
        return
    # {"answer": {...}} / {"finding": {...}} / {"reply": "..."}: a model that wrapped each object.
    keys = [k for k in obj if k != REPEATED_KEYS]
    if len(keys) == 1 and str(keys[0]).lower() in _WRAPPER_KINDS:
        kind, value = str(keys[0]).lower(), obj[keys[0]]
        if isinstance(value, dict):
            yield from _unwrap({"kind": kind, **value})
            return
        if kind == "reply" and isinstance(value, str):
            yield {"kind": "reply", "text": value}
            return
    if "box_2d" in obj or "kind" in obj or "marks_awarded" in obj or "parts" in obj:
        nested = obj.pop("findings", None) if str(obj.get("kind") or "answer").lower() == "answer" else None
        yield obj
        # The contract nests each answer's findings in it (Gemma 4 leaves findings out when
        # they are separate array elements); flat findings after their answer still work.
        for finding in nested if isinstance(nested, list) else ():
            if isinstance(finding, dict):
                yield {"kind": "finding", **finding, "answer_id": finding.get("answer_id") or obj.get("id")}
        return
    for value in obj.values():
        if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            for item in value:
                yield from _unwrap(item)
            return



_REDO_ID = re.compile(r"[_-]?(revised|revision|corrected|correction|fixed|final|updated|v\d+)$", re.I)


def _location_key(raw):
    return json.dumps([raw.get(k) for k in ("page", "box_2d", "lines", "blocks", "parts")], sort_keys=True, default=str)


def settle_answers(objects):
    """Drop an answer that the model immediately redoes.

    Some models (Gemma 4) change their mind mid-reply: "...Wait, the image shows 1947. Let's
    re-evaluate." followed by a second answer for the same question ("q16_revised"). The later
    answer is its final verdict, so it replaces the earlier one and that one's findings. Each
    answer is held until the next answer arrives, which delays the stream by one answer.
    """
    held = []
    for obj in objects:
        if str(obj.get("kind") or "answer").lower() == "answer" and "answer_id" not in obj:
            if held and _redoes(held[0], obj):
                held = []
            yield from held
            held = [obj]
        elif held:
            held.append(obj)
        else:
            yield obj
    yield from held


def _redoes(first, second):
    label = str(first.get("question") or "").strip().lower()
    if not label or label != str(second.get("question") or "").strip().lower():
        return False
    first_id, second_id = str(first.get("id") or ""), str(second.get("id") or "")
    renamed = bool(first_id) and second_id != first_id and second_id.startswith(first_id) and \
        bool(_REDO_ID.search(second_id[len(first_id):]))
    return renamed or _location_key(first) == _location_key(second)


class _Reply:
    """Wraps a token stream and keeps the text, so an unreadable reply can be reported."""

    def __init__(self, tokens):
        self.tokens, self.chunks = tokens, []

    def __iter__(self):
        for token in self.tokens:
            self.chunks.append(token)
            yield token

    @property
    def text(self):
        return "".join(self.chunks).strip()


_EMPTY_REPLY = re.compile(r"(```(?:json)?\s*)?\[\s*\](\s*```)?")


def check_readable(reply, items_read, model_code):
    """Raise when the model said something but no answer, finding or reply could be read from it."""
    text = reply.text
    if items_read or not text or _EMPTY_REPLY.fullmatch(text):
        return
    logger.warning("Unreadable evaluation reply from %s (%d chars): %.4000s", model_code, len(text), text)
    name = model_code.split("/", 1)[-1]
    raise EvaluationError(f"{name} replied ({len(text)} characters), but not in the JSON format the app reads, "
                          "so nothing could be shown. Its reply is in the backend log. Try again, or adjust the "
                          "system prompt.")


def _load_image(image_url):
    """Download an image and return (data_url, width, height) with EXIF rotation applied."""
    response = requests.get(image_url, timeout=60)
    response.raise_for_status()
    img = PILImage.open(io.BytesIO(response.content))
    rotated = ImageOps.exif_transpose(img)
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
    if rotated is img and content_type in ("image/png", "image/jpeg", "image/webp"):
        data = response.content
    else:
        buf = io.BytesIO()
        rotated.convert("RGB").save(buf, format="PNG")
        data, content_type = buf.getvalue(), "image/png"
    encoded = base64.b64encode(data).decode("ascii")
    width, height = rotated.size
    return f"data:{content_type};base64,{encoded}", width, height


@dataclass
class SheetPage:
    """One student answer-sheet page: its 1-based number, signed URL and pixel size."""
    number: int
    url: str
    width: int = None
    height: int = None


def page_sizes_of(pages):
    return {p.number: (p.width, p.height) for p in pages if p.width and p.height}


def _load_pages(pages):
    """[(page number, data URL)] for the pages, filling in any missing sizes from the image."""
    loaded = []
    for page in pages:
        data_url, width, height = _load_image(page.url)
        if not (page.width and page.height):
            page.width, page.height = width, height
        loaded.append((page.number, data_url))
    return loaded


def _context_parts(reference_data_urls, instructions):
    parts = []
    references = list(reference_data_urls)[:MAX_REFERENCE_PAGES]
    for i, url in enumerate(references, start=1):
        parts.append({"type": "text", "text": f"REFERENCE page {i} of {len(references)} (question paper / answer key):"})
        parts.append({"type": "image_url", "image_url": {"url": url}})
    instructions = _text(instructions, MAX_INSTRUCTIONS_CHARS)
    if instructions:
        parts.append({
            "type": "text",
            "text": f"TEACHER INSTRUCTIONS (from the teacher, not the student):\n<<<\n{instructions}\n>>>",
        })
    return parts


def _sheet_parts(loaded_pages, total_pages):
    parts = []
    for number, data_url in loaded_pages:
        parts.append({"type": "text", "text": f"STUDENT ANSWER SHEET page {number} of {total_pages}:"})
        parts.append({"type": "image_url", "image_url": {"url": data_url}})
    return parts


def build_user_content(loaded_pages, total_pages, reference_data_urls=(), instructions=""):
    content = _context_parts(reference_data_urls, instructions)
    content += _sheet_parts(loaded_pages, total_pages)
    content.append({"type": "text", "text": EVALUATE_REQUEST})
    return content


# ── Re-evaluation from teacher feedback ──────────────────────────────────────

REVISION_SCOPES = ("answer", "page", "document")
MAX_FEEDBACK_CHARS = 2000
MAX_HISTORY_TURNS = 5

REVISION_PROMPT = """

---
REVISION
You are now REVISING an earlier evaluation because the teacher sent feedback.
- PREVIOUS EVALUATION is the current evaluation of the whole sheet in the same JSON format. It may include edits the teacher made by hand.
{pages_note}- Apply the TEACHER FEEDBACK. Look at the student's work again wherever the feedback points; keep the parts of the previous evaluation that the feedback does not affect, unless they are clearly wrong.
- When the teacher's feedback conflicts with the answer key or with your own judgement, follow the teacher.
- Begin the array with exactly one object {{"kind": "reply", "text": "..."}}: 1 to 3 sentences to the teacher saying what you changed and why, or why you kept something unchanged.
{scope_rule}"""

_IMAGE_PAGES_NOTE = ("- Only some sheet pages may be attached; they are the pages the revision is about. Keep the parts "
                     "and findings on pages that are not attached exactly as they are in the previous evaluation.\n")

_SCOPE_RULES = {
    "document": ("- Then return the revised evaluation of the sheet: every answer, each with everything it covers and its findings. "
                 "Keep the ids of existing answers; an answer you leave out is kept unchanged."),
    "page": ("- Then return, complete with everything they cover on every page and their findings, the revised versions of the "
             "answers listed under SCOPE, plus any answer on page {page} that the previous evaluation missed. "
             "Keep their ids; an answer you leave out is kept unchanged. Do not return any other answer."),
    "answer": ('- Then return ONLY the revised answer with id "{answer_id}" (keep that id), with everything it covers on '
               "every page and its findings. Do not return any other answer."),
}


@dataclass
class Revision:
    """What the teacher asked for. ``previous`` is the sheet's current annotation list."""
    feedback: str
    scope: str = "page"
    answer_id: str = None
    page: int = None  # 1-based; the page a "page" revision is about
    previous: list = field(default_factory=list)
    history: list = field(default_factory=list)  # [{"feedback": ..., "reply": ...}], oldest first
    transcript: dict = None  # the sheet's OCR transcript, for text-only models (kept from the first run)

    def _answers(self):
        return [i for i in self.previous if i.get("kind") == "answer"]

    @property
    def target(self):
        if self.scope != "answer":
            return None
        return next((a for a in self._answers() if a.get("id") == self.answer_id), None)

    @property
    def target_ids(self):
        """Ids of the answers this revision may replace."""
        if self.scope == "answer":
            return {self.answer_id}
        if self.scope == "page":
            return {a["id"] for a in self._answers() if self.page in answer_pages(a)}
        return {a["id"] for a in self._answers()}

    def pages_needed(self, total_pages):
        """Sheet pages to show the model: every page a target answer or its findings is on."""
        if self.scope == "document":
            return list(range(1, total_pages + 1))
        targets = self.target_ids
        pages = {self.page} if self.scope == "page" and self.page else set()
        for item in self.previous:
            if item.get("kind") == "answer" and item.get("id") in targets:
                pages.update(answer_pages(item))
            elif item.get("kind") == "finding" and item.get("answer_id") in targets and item.get("page"):
                pages.add(item["page"])
        return sorted(p for p in pages if 1 <= p <= total_pages)


def build_revision_prompt(max_marks, revision, mode="image"):
    rule = _SCOPE_RULES[revision.scope].format(answer_id=revision.answer_id, page=revision.page)
    return build_evaluation_prompt(max_marks, mode) + REVISION_PROMPT.format(
        pages_note=_IMAGE_PAGES_NOTE if mode in ("image", "hybrid") else "", scope_rule=rule)


def to_model_format(items, page_sizes):
    """Annotation dicts (pixel boxes) → the JSON shape the model reads and writes (box_2d, 0-1000)."""
    sizes = {int(k): v for k, v in page_sizes.items()}
    out = []
    for item in items:
        if not isinstance(item, dict) or item.get("kind") not in ("answer", "finding"):
            continue
        raw = {k: v for k, v in item.items() if k not in ("box", "parts")}
        if item["kind"] == "answer":
            raw["parts"] = [{"page": p["page"], "box_2d": _to_box_2d(p["box"], *sizes[p["page"]])}
                            for p in item.get("parts") or [] if p.get("box") and p.get("page") in sizes]
        elif item.get("box") and item.get("page") in sizes:
            raw["box_2d"] = _to_box_2d(item["box"], *sizes[item["page"]])
        out.append(raw)
    return out


def build_revision_content(loaded_pages, total_pages, reference_data_urls, instructions, previous_raw, revision):
    content = _context_parts(reference_data_urls, instructions)
    content += _sheet_parts(loaded_pages, total_pages)
    content.append({"type": "text", "text": "PREVIOUS EVALUATION:\n" + json.dumps(previous_raw, ensure_ascii=False)})
    history = [h for h in revision.history if h.get("feedback")][-MAX_HISTORY_TURNS:]
    if history:
        lines = [f"- Teacher: {_text(h['feedback'], 500)}\n  You replied: {_text(h.get('reply'), 500)}" for h in history]
        content.append({"type": "text", "text": "EARLIER FEEDBACK (already applied):\n" + "\n".join(lines)})
    content.append({"type": "text", "text": _feedback_block(revision)})
    return content


def _feedback_block(revision):
    """The scope and the teacher's feedback, as the last thing the model reads."""
    scope = ""
    if revision.scope == "answer":
        target = revision.target or {}
        about = f'the answer {target.get("question") or revision.answer_id} (id "{revision.answer_id}")'
    elif revision.scope == "page":
        ids = ", ".join(f'"{i}"' for i in sorted(revision.target_ids)) or "none yet"
        about = f"page {revision.page}"
        scope = f"SCOPE: answers on page {revision.page}: {ids}\n"
    else:
        about = "the whole answer sheet"
    return (f"{scope}TEACHER FEEDBACK about {about}:\n<<<\n{_text(revision.feedback, MAX_FEEDBACK_CHARS)}\n>>>\n"
            "Return the reply object and then the revised JSON as described.")


def revise_objects(raw_objects, page_sizes, max_marks, revision):
    """Normalise a model's revision output: yields {"kind": "reply"} and annotation dicts."""
    targets = revision.target_ids
    reserved, out_of_scope = set(), set()
    if revision.scope != "document":
        for item in revision.previous:
            owner = item.get("id") if item.get("kind") == "answer" else item.get("answer_id")
            if owner not in targets:
                reserved.add(item.get("id"))
                reserved.update(p.get("id") for p in item.get("parts") or [])
                if item.get("kind") == "answer":
                    out_of_scope.add(str(item.get("id")))
    normalizer = EvaluationNormalizer(page_sizes, max_marks, reserved_ids=reserved)
    replied = False
    for raw in raw_objects:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("kind", "")).lower() == "reply":
            if not replied:
                replied = True
                yield {"kind": "reply", "text": _text(raw.get("text"), 1500)}
            continue
        # The model was told not to return answers outside the scope; if it does, ignore them
        # (and their findings) rather than letting them come back as duplicates.
        owner = raw.get("id") if raw.get("kind") == "answer" else raw.get("answer_id")
        if str(owner) in out_of_scope:
            continue
        item = normalizer.add(raw)
        if item:
            yield item


def merge_revision(previous, revised, revision):
    """The sheet's new annotation list after a revision.

    Each returned answer replaces the answer with the same id, in place, together with
    all of that answer's findings. Answers in scope that the model left out are kept
    unchanged (a model dropping an answer must not silently delete its marks); answers
    out of scope are never touched; new answers are added at the end. An answer
    revision keeps the answer's id, and its old boxes when the model returns none.
    """
    revised = [i for i in revised if i.get("kind") in ("answer", "finding")]
    known = {i.get("id") for i in previous if i.get("kind") == "answer"}
    answers = [i for i in revised if i.get("kind") == "answer"]
    rename = {}
    if revision.scope == "answer":
        old = revision.target
        if old is None:
            raise EvaluationError("That answer is no longer on this sheet.")
        if not answers:
            raise EvaluationError("The model did not return a revised answer.")
        new = answers[0]
        rename = {new["id"]: revision.answer_id}
        answers = [{**new, "id": revision.answer_id, "parts": new.get("parts") or old.get("parts") or [],
                    "question": new.get("question") or old.get("question")}]
    elif revision.scope == "page":
        targets = revision.target_ids
        answers = [a for a in answers if a["id"] in targets or a["id"] not in known]

    by_id = {a["id"]: a for a in answers}
    findings = {}
    for f in revised:
        owner = rename.get(f.get("answer_id"), f.get("answer_id"))
        if f.get("kind") == "finding" and owner in by_id:
            findings.setdefault(owner, []).append({**f, "answer_id": owner})

    merged = []
    for item in previous:
        if item.get("kind") == "answer" and item.get("id") in by_id:
            merged.append(by_id[item["id"]])
            merged.extend(findings.get(item["id"], []))
        elif item.get("kind") == "finding" and item.get("answer_id") in by_id:
            continue  # replaced by the revised answer's findings
        else:
            merged.append(item)
    for answer in answers:
        if answer["id"] not in known:
            merged.append(answer)
            merged.extend(findings.get(answer["id"], []))
    return merged


def scope_score(items, answer_ids):
    """(marks awarded, max marks) over the given answers."""
    answers = [i for i in items if i.get("kind") == "answer" and i.get("id") in answer_ids]
    return (sum(_number(a.get("marks_awarded")) or 0 for a in answers),
            sum(_number(a.get("max_marks")) or 0 for a in answers))


# ── OCR transcripts, for text-only models ────────────────────────────────────
# A text-only model (DeepSeek V4 Flash on Sarvam) cannot see the pages. Each page is OCR'd
# into numbered lines with their boxes; the model answers with line ids ("3.12" = page 3,
# line 12) and the server turns those back into boxes, so boxes come from OCR, not from
# the model guessing coordinates.

DEFAULT_TRANSCRIPT_OCR_MODEL = "google-ocr/gemini-2.5-flash"
LINE_REF = re.compile(r"(\d+)\D+?(\d+)")


def ocr_transcribe_page(page, log_context=None):
    """OCR one SheetPage into reading-order lines: [{"text", "box": [x1, y1, x2, y2]}].

    Uses the OCR arena's own models (EVAL_OCR_MODEL, a Gemini OCR model by default), which
    return regions; each region's text lines get an equal slice of the region's height.
    """
    from ai_model.ocr_interactions import get_ocr_output

    model = os.getenv("EVAL_OCR_MODEL") or DEFAULT_TRANSCRIPT_OCR_MODEL
    lines = []
    for region in get_ocr_output(page.url, model=model, generate_text=True, log_context=log_context) or []:
        texts = [t.strip() for t in str(region.get("text") or "").splitlines() if t.strip()]
        x1, y1, x2, y2 = region.get("box") or (0, 0, 0, 0)
        for i, text in enumerate(texts):
            top = y1 + (y2 - y1) * i / len(texts)
            lines.append({"text": text, "box": [x1, round(top), x2, round(top + (y2 - y1) / len(texts))]})
    return lines


# What build_transcript calls; a deployment with a line-level OCR engine can swap it in.
transcribe_page = ocr_transcribe_page


PICTURE_TYPES = ("picture", "figure", "image", "chart", "diagram")


def _keep_line(ln):
    """Text lines, and pictures (drawn answers) even though they have no text."""
    return bool(str(ln.get("text") or "").strip()) or str(ln.get("type") or "").lower() in PICTURE_TYPES


def transcribe_page_lines(page, log_context=None):
    """The transcript entries of one page: [{"id": "p.n", "text", "box"[, "type"]}]."""
    lines = _transcriber()(page, log_context)
    out = []
    for ln in lines:
        if not _keep_line(ln):
            continue
        entry = {"id": f"{page.number}.{len(out) + 1}", "text": str(ln.get("text") or "").strip(),
                 "box": [int(v) for v in ln["box"]]}
        if ln.get("type"):
            entry["type"] = str(ln["type"])
        out.append(entry)
    return out


def build_transcript(pages, log_context=None, on_page=None):
    """{"pages": [{"number", "width", "height", "lines": [{"id": "p.l", "text", "box"}]}]}."""
    out = []
    for page in pages:
        if on_page:
            on_page(page)
        lines = transcribe_page_lines(page, log_context)
        out.append({"number": page.number, "width": page.width, "height": page.height, "lines": lines})
    return {"pages": out}


def ocr_pages(pages, log_context=None):
    """Generator: OCR the pages (concurrently for Bodhan), yielding {"kind": "status"} notes;
    returns the transcript. Use as ``transcript = yield from ocr_pages(...)``."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    engine = transcript_engine_name()
    workers = _env_number("BODHAN_OCR_CONCURRENCY", 4, int) if engine == "Bodhan indic-ocr" else 1
    results = {}
    yield {"kind": "status", "text": f"Reading {len(pages)} page(s) with {engine}…"}
    if workers <= 1 or len(pages) == 1:  # local OCR engines run in the request thread
        for done, page in enumerate(pages, start=1):
            results[page.number] = transcribe_page_lines(page, log_context)
            yield {"kind": "status", "text": f"Read page {page.number} with {engine} ({done} of {len(pages)})…"}
        return {"pages": [{"number": p.number, "width": p.width, "height": p.height, "lines": results[p.number]}
                          for p in pages]}
    with ThreadPoolExecutor(max_workers=min(workers, len(pages))) as pool:
        futures = {pool.submit(transcribe_page_lines, page, log_context): page for page in pages}
        for done, future in enumerate(as_completed(futures), start=1):
            page = futures[future]
            results[page.number] = future.result()
            yield {"kind": "status", "text": f"Read page {page.number} with {engine} ({done} of {len(pages)})…"}
    return {"pages": [{"number": p.number, "width": p.width, "height": p.height, "lines": results[p.number]}
                      for p in pages]}


def _line_label(ln):
    kind = ln.get("type")
    return f"[{ln['id']}] ({kind}) {ln['text']}".rstrip() if kind else f"[{ln['id']}] {ln['text']}"


def page_transcript_text(page):
    return "\n".join(_line_label(ln) for ln in page["lines"]) or "(the OCR found no text on this page)"


def transcript_text(transcript):
    blocks = []
    for page in transcript["pages"]:
        blocks.append(f"--- Page {page['number']} of {len(transcript['pages'])} ---")
        blocks.extend(_line_label(ln) for ln in page["lines"])
    return "\n".join(blocks)


class LineIndex:
    """Resolves the model's line ids (and ranges) to pages and boxes, and boxes back to ids."""

    def __init__(self, transcript):
        self.lines = {}
        self.texts = {}
        self.types = {}
        self.order = []
        for page in transcript["pages"]:
            for ln in page["lines"]:
                self.lines[ln["id"]] = (page["number"], ln["box"])
                self.texts[ln["id"]] = ln.get("text") or ""
                self.types[ln["id"]] = ln.get("type") or ""
                self.order.append(ln["id"])

    def _key(self, ref):
        match = LINE_REF.search(str(ref))
        return f"{int(match.group(1))}.{int(match.group(2))}" if match else None

    def ids(self, refs):
        """Line ids in transcript order; "3.4-3.9" (or "3.4-9") is expanded. Unknown ids are dropped."""
        if isinstance(refs, (str, int, float)):
            refs = [refs]
        wanted = set()
        for ref in refs or []:
            text = str(ref)
            if "-" in text:
                start, _, end = text.partition("-")
                first = self._key(start)
                if first and not LINE_REF.search(end) and end.strip().isdigit():
                    end = f"{first.split('.')[0]}.{end.strip()}"
                last = self._key(end)
                if first in self.lines and last in self.lines:
                    i, j = sorted((self.order.index(first), self.order.index(last)))
                    wanted.update(self.order[i:j + 1])
                    continue
            key = self._key(text)
            if key in self.lines:
                wanted.add(key)
        return [i for i in self.order if i in wanted]

    def page_boxes(self, refs):
        """[(page, union box of that page's lines)] in page order."""
        by_page = {}
        for line_id in self.ids(refs):
            page, box = self.lines[line_id]
            by_page.setdefault(page, []).append(box)
        return [(page, [min(b[0] for b in boxes), min(b[1] for b in boxes),
                        max(b[2] for b in boxes), max(b[3] for b in boxes)])
                for page, boxes in sorted(by_page.items())]

    def box_of(self, ref):
        key = self._key(ref)
        return self.lines.get(key) if key else None

    def containing(self, page, box):
        """Ids of the lines/blocks on ``page`` that contain the centre of ``box``."""
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        return [line_id for line_id in self.order
                if self.lines[line_id][0] == page
                and self.lines[line_id][1][0] <= cx <= self.lines[line_id][1][2]
                and self.lines[line_id][1][1] <= cy <= self.lines[line_id][1][3]]

    def within(self, page, box):
        """Ids of the lines on ``page`` whose centre lies inside ``box``."""
        x1, y1, x2, y2 = box
        found = []
        for line_id in self.order:
            line_page, (a, b, c, d) = self.lines[line_id]
            if line_page == page and x1 <= (a + c) / 2 <= x2 and y1 <= (b + d) / 2 <= y2:
                found.append(line_id)
        return found


def _compact(ids):
    """["3.1", "3.2", "3.3", "4.1"] -> ["3.1-3.3", "4.1"], to keep prompts short."""
    out, run = [], []
    for line_id in ids:
        page, number = (int(x) for x in line_id.split("."))
        if run and run[-1][0] == page and run[-1][1] == number - 1:
            run.append((page, number))
        else:
            if run:
                out.append(f"{run[0][0]}.{run[0][1]}" + (f"-{run[-1][0]}.{run[-1][1]}" if len(run) > 1 else ""))
            run = [(page, number)]
    if run:
        out.append(f"{run[0][0]}.{run[0][1]}" + (f"-{run[-1][0]}.{run[-1][1]}" if len(run) > 1 else ""))
    return out


def resolve_lines(raw, index, page_sizes):
    """A model object that names transcript "lines" -> the box_2d shape the normalizer reads."""
    if not isinstance(raw, dict) or "lines" not in raw:
        return raw
    boxes = index.page_boxes(raw.get("lines"))
    resolved = {k: v for k, v in raw.items() if k != "lines"}
    as_2d = lambda page, box: _to_box_2d(box, *page_sizes[page])  # noqa: E731
    if str(raw.get("kind", "")).lower() == "finding" or ("answer_id" in raw and "marks_awarded" not in raw):
        if boxes:
            page, box = boxes[0]
            resolved.update(page=page, box_2d=as_2d(page, box))
    else:
        resolved["parts"] = [{"page": page, "box_2d": as_2d(page, box)} for page, box in boxes]
    return resolved


def to_text_model_format(items, index):
    """Annotation dicts -> the line-id shape a text-only model reads and writes."""
    out = []
    for item in items:
        if not isinstance(item, dict) or item.get("kind") not in ("answer", "finding"):
            continue
        raw = {k: v for k, v in item.items() if k not in ("box", "parts", "page")}
        if item["kind"] == "answer":
            ids = [i for p in item.get("parts") or [] if p.get("box") for i in index.within(p["page"], p["box"])]
        else:
            ids = index.within(item.get("page"), item["box"]) if item.get("box") else []
        raw["lines"] = _compact(ids)
        out.append(raw)
    return out


def reference_pages_text(reference_urls, log_context=None):
    """The OCR text of each question paper / answer key page."""
    pages = [SheetPage(i, url) for i, url in enumerate(list(reference_urls)[:MAX_REFERENCE_PAGES], start=1)]
    transcribe = _transcriber()
    return ["\n".join(str(ln.get("text") or "") for ln in transcribe(page, log_context) if str(ln.get("text") or "").strip())
            for page in pages]


def reference_text(reference_urls, log_context=None, texts=None):
    """The question paper / answer key as plain text, page by page."""
    texts = reference_pages_text(reference_urls, log_context) if texts is None else texts
    return "\n".join(f"--- Reference page {i} ---\n{text}" for i, text in enumerate(texts, start=1))


def kept_reference_texts(transcript, reference_urls, log_context=None):
    """The answer key's OCR text kept with the sheet's transcript, or a fresh OCR of it.
    Kept so that chat re-evaluations do not OCR (and pay for) the same pages again."""
    kept = (transcript or {}).get("reference_texts")
    if kept is not None and len(kept) == len(list(reference_urls)[:MAX_REFERENCE_PAGES]):
        return kept
    return reference_pages_text(reference_urls, log_context) if reference_urls else []


def build_text_user_content(transcript, reference, instructions):
    parts = []
    if reference:
        parts.append("REFERENCE (question paper / answer key, OCR text):\n" + reference)
    instructions = _text(instructions, MAX_INSTRUCTIONS_CHARS)
    if instructions:
        parts.append(f"TEACHER INSTRUCTIONS (from the teacher, not the student):\n<<<\n{instructions}\n>>>")
    parts.append("STUDENT ANSWER SHEET (OCR transcript):\n" + transcript_text(transcript))
    parts.append(EVALUATE_REQUEST)
    return "\n\n".join(parts)


# ── Bodhan document OCR (indic-ocr) ──────────────────────────────────────────
# Verified against console.bodhan.ai/api-docs and the Bodhan AI Cookbook: POST
# {base}/v1/chat/completions with a Bearer key, model "indic-ocr", ONE PNG or JPEG page per
# request as a base64 data URI (PDFs are not accepted). The reply has the page as Markdown in
# choices[0].message.content and a top-level "blocks" list of layout regions:
# {order, label, type, bbox_xyxy: [x1, y1, x2, y2] in pixels of the image sent, conf, text}.
# Blocks are paragraphs / lists / tables / pictures, not lines. HTTP 502 means a block hit
# max_tokens (default 2048 per block) or the image could not be decoded.

BODHAN_DEFAULT_BASE_URL = "https://api.bodhan.ai"
BODHAN_OCR_MODEL = "indic-ocr"
BODHAN_OCR_ENGINE = "Bodhan indic-ocr"
BODHAN_OCR_MAX_SIDE = 2400
BODHAN_OCR_PNG_LIMIT = 6 * 1024 * 1024


def bodhan_ocr_configured():
    return bool(os.getenv("BODHAN_API_KEY", "").strip())


def _bodhan_page_image(img):
    """(data URI, scale) for a page: PNG unless that is large, then JPEG; long side <= max."""
    max_side = _env_number("BODHAN_OCR_MAX_SIDE", BODHAN_OCR_MAX_SIDE, int)
    scale = min(1.0, max_side / max(img.size))
    if scale < 1.0:
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), PILImage.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    if buf.tell() <= BODHAN_OCR_PNG_LIMIT:
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii"), scale
    return _jpeg_data_url(img, max(img.size), 92), scale


def bodhan_ocr_page(image_url, log_context=None):
    """OCR one page with Bodhan's indic-ocr: blocks in reading order, boxes in the page's pixels.

    [{"text", "box": [x1, y1, x2, y2], "type", "label", "conf"}]
    """
    key = os.getenv("BODHAN_API_KEY", "").strip()
    if not key:
        raise EvaluationError("BODHAN_API_KEY is not configured on the server.")
    base = (os.getenv("BODHAN_BASE_URL") or BODHAN_DEFAULT_BASE_URL).rstrip("/")
    img = _fetch_image(image_url)
    width, height = img.size
    data_url, scale = _bodhan_page_image(img)
    body = {
        "model": BODHAN_OCR_MODEL,
        "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": data_url}}]}],
        "table_format": os.getenv("BODHAN_OCR_TABLE_FORMAT") or "markdown",
    }
    response = requests.post(f"{base}/v1/chat/completions", json=body,
                             headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                             timeout=_env_number("BODHAN_OCR_TIMEOUT", 180))
    if response.status_code >= 400:
        try:
            error = response.json().get("error") or {}
            detail = f"{error.get('message')} (code {error.get('code')}, request_id {error.get('request_id')})"
        except ValueError:
            detail = _text(response.text, 300)
        if response.status_code in (401, 403):
            raise EvaluationError(f"Bodhan rejected the API key (HTTP {response.status_code}): {detail}")
        if response.status_code == 429:
            raise EvaluationError(f"Bodhan OCR rate limit reached (HTTP 429). Wait a minute and try again: {detail}")
        raise EvaluationError(f"Bodhan OCR error (HTTP {response.status_code}): {detail}")

    blocks = []
    for block in sorted(response.json().get("blocks") or [], key=lambda b: _number(b.get("order")) or 0):
        bbox = block.get("bbox_xyxy")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4 or any(_number(v) is None for v in bbox):
            continue
        x1, y1, x2, y2 = (float(v) / scale for v in bbox)
        box = [max(0, min(width, round(min(x1, x2)))), max(0, min(height, round(min(y1, y2)))),
               max(0, min(width, round(max(x1, x2)))), max(0, min(height, round(max(y1, y2))))]
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            continue
        blocks.append({"text": str(block.get("text") or "").strip(), "box": box,
                       "type": str(block.get("type") or block.get("label") or "Text"),
                       "label": block.get("label"), "conf": block.get("conf")})
    return blocks


def bodhan_transcribe_page(page, log_context=None):
    return bodhan_ocr_page(page.url, log_context)


def _transcriber():
    """The OCR used for transcripts: Bodhan's indic-ocr when BODHAN_API_KEY is set (unless
    EVAL_TRANSCRIPT_OCR=default), else the swappable ``transcribe_page`` hook."""
    choice = (os.getenv("EVAL_TRANSCRIPT_OCR") or "").strip().lower()
    if choice == "bodhan" or (choice != "default" and bodhan_ocr_configured()):
        return bodhan_transcribe_page
    return transcribe_page


def transcript_engine_name():
    return BODHAN_OCR_ENGINE if _transcriber() is bodhan_transcribe_page else "OCR"


def _box_area(box):
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def _intersect(a, b):
    box = [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]
    return box if box[2] > box[0] and box[3] > box[1] else None


def _union_boxes(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _pixel_boxes(raw_box, size):
    """box_2d (or a list of them) -> pixel boxes."""
    if isinstance(raw_box, (list, tuple)) and raw_box and all(isinstance(b, (list, tuple)) for b in raw_box):
        return [b for b in (_to_pixel_box(b, *size) for b in raw_box) if b]
    box = _to_pixel_box(raw_box, *size)
    return [box] if box else []


def _within_blocks(model_box, block_box):
    """The model's box kept inside the OCR block it names, or None when it is mostly outside
    (models estimate coordinates poorly; the block is the reliable fallback)."""
    inside = _intersect(model_box, block_box)
    return inside if inside and _box_area(inside) >= 0.5 * _box_area(model_box) else None


NUMBERED_LINE = re.compile(r"^\s*(?:Q\.?\s*)?\(?(\d{1,3})\s*[.)]")


def question_number(label):
    match = re.search(r"\d+", str(label or ""))
    return int(match.group()) if match else None


def slice_for_question(box, text, number, kind=""):
    """The part of an OCR block that holds question ``number`` when the OCR merged several
    numbered questions into one block (e.g. "05. … / 06. … / 07. …"): the block's text lines
    are given equal heights, and the slice runs from the line starting with that number to the
    next numbered line. None when the block is not such a merge (or is a table)."""
    if number is None or str(kind).lower() == "table" or str(text).lstrip().startswith("<"):
        return None
    lines = [ln for ln in str(text or "").split("\n") if ln.strip()]
    numbered = [(i, int(m.group(1))) for i, ln in enumerate(lines) if (m := NUMBERED_LINE.match(ln))]
    if len(numbered) < 2:
        return None
    start = next((i for i, n in numbered if n == number), None)
    if start is None:
        return None
    end = next((i for i, _ in numbered if i > start), len(lines))
    height = (box[3] - box[1]) / len(lines)
    return [box[0], round(box[1] + start * height), box[2], round(box[1] + end * height)]


class HybridResolver:
    """Turns hybrid-mode model objects (block ids) into the box_2d shape the normalizer reads.

    Answers: one part per page, the union of the OCR blocks named, where a block the OCR merged
    from several numbered questions is cut down to this question's lines; a box the model gives
    on that page refines it only when it lies inside; a model box on a page with no named block
    (the OCR missed that piece) is used as is. Findings: the named block, kept inside its
    answer's region, or the model's tighter box inside that.
    """

    def __init__(self, index, page_sizes):
        self.index, self.page_sizes = index, page_sizes
        self.answer_regions = {}  # model answer id -> {page: pixel box}

    def _as_2d(self, page, box):
        return _to_box_2d(box, *self.page_sizes[page])

    def _named(self, raw, number=None):
        """{page: union box} of the named blocks, each sliced to ``number`` when merged."""
        refs = raw.get("blocks", raw.get("lines"))
        boxes = {}
        for block_id in self.index.ids(refs) if refs is not None else []:
            page, box = self.index.lines[block_id]
            box = slice_for_question(box, self.index.texts.get(block_id), number,
                                     self.index.types.get(block_id)) or box
            boxes.setdefault(page, []).append(box)
        return {page: _union_boxes(b) for page, b in boxes.items()}

    def _model_boxes(self, part_or_raw, page):
        boxes = _pixel_boxes(part_or_raw.get("box_2d") or part_or_raw.get("box"), self.page_sizes[page])
        return _union_boxes(boxes) if boxes else None

    def resolve(self, raw):
        if not isinstance(raw, dict):
            return raw
        resolved = {k: v for k, v in raw.items() if k not in ("blocks", "lines", "parts", "box_2d", "box", "page")}
        if str(raw.get("kind", "")).lower() == "finding" or ("answer_id" in raw and "marks_awarded" not in raw):
            return self._finding(raw, resolved)

        named = self._named(raw, question_number(raw.get("question")))
        explicit = {}
        raw_parts = raw.get("parts") if isinstance(raw.get("parts"), list) else []
        for part in (piece for part in raw_parts if isinstance(part, dict) for piece in [part, *part.get(REPEATED_KEYS, [])]):
            page = _page_number(part.get("page"))
            if page in self.page_sizes:
                box = self._model_boxes(part, page)
                if box:
                    explicit.setdefault(page, []).append(box)
        regions = {}
        for page in sorted(set(named) | set(explicit)):
            model = _union_boxes(explicit[page]) if explicit.get(page) else None
            if page in named:
                regions[page] = (_within_blocks(model, named[page]) if model else None) or named[page]
            else:
                regions[page] = model
        if raw.get("id") is not None:
            self.answer_regions[str(raw["id"])] = regions
        resolved["parts"] = [{"page": page, "box_2d": self._as_2d(page, box)} for page, box in regions.items() if box]
        return resolved

    def _finding(self, raw, resolved):
        named = self._named(raw)
        answer = self.answer_regions.get(str(raw.get("answer_id")), {})
        page = next(iter(named), None) or _page_number(raw.get("page")) or next(iter(answer), None)
        if page not in self.page_sizes:
            return resolved
        region = named.get(page)
        if region and answer.get(page):
            region = _intersect(region, answer[page]) or answer[page]
        region = region or answer.get(page)
        model = self._model_boxes(raw, page)
        if region:
            box = (_within_blocks(model, region) if model else None) or region
        else:
            box = model
        if box:
            resolved.update(page=page, box_2d=self._as_2d(page, box))
        return resolved


def resolve_blocks(raw, index, page_sizes):
    """One object at a time, without memory of earlier answers (see HybridResolver)."""
    return HybridResolver(index, page_sizes).resolve(raw)


def to_hybrid_model_format(items, index, page_sizes):
    """Annotation dicts -> what a hybrid model reads and writes: block ids plus each box."""
    out = []
    for raw, item in zip(to_model_format(items, page_sizes), (i for i in items
                                                              if isinstance(i, dict) and i.get("kind") in ("answer", "finding"))):
        if item["kind"] == "answer":
            ids = [i for p in item.get("parts") or [] if p.get("box")
                   for i in (index.within(p["page"], p["box"]) or index.containing(p["page"], p["box"]))]
        else:
            ids = index.containing(item.get("page"), item["box"]) if item.get("box") else []
        out.append({**raw, "blocks": _compact(ids)})
    return out


def build_hybrid_user_content(loaded_pages, transcript, reference_images, reference_texts, instructions):
    """Reference images with their OCR text, instructions, then each sheet page image followed
    by its OCR blocks."""
    content = []
    total = len(reference_images)
    for i, url in enumerate(reference_images, start=1):
        content.append({"type": "text", "text": f"REFERENCE page {i} of {total} (question paper / answer key):"})
        content.append({"type": "image_url", "image_url": {"url": url}})
        if i <= len(reference_texts) and reference_texts[i - 1].strip():
            content.append({"type": "text", "text": f"OCR text of reference page {i}:\n{reference_texts[i - 1]}"})
    instructions = _text(instructions, MAX_INSTRUCTIONS_CHARS)
    if instructions:
        content.append({"type": "text",
                        "text": f"TEACHER INSTRUCTIONS (from the teacher, not the student):\n<<<\n{instructions}\n>>>"})
    pages = {p["number"]: p for p in transcript["pages"]}
    for number, url in loaded_pages:
        content.append({"type": "text", "text": f"STUDENT ANSWER SHEET page {number} of {len(pages)}:"})
        content.append({"type": "image_url", "image_url": {"url": url}})
        content.append({"type": "text", "text": f"OCR BLOCKS of page {number}:\n{page_transcript_text(pages[number])}"})
    return content


# ── Sarvam (OpenAI-compatible chat completions) ──────────────────────────────
# Verified against Bodhan-Classroom's Sarvam provider: POST {base}/chat/completions with an
# `api-subscription-key` header (not a Bearer token); the hosted open-source models such as
# deepseekv4-flash are served from /v2, which needs beta access on the Sarvam account.
# Without max_tokens Sarvam caps a reply at 2048 tokens, reasoning included, so it is
# always sent. DeepSeek V4 Flash reasons on every call (reasoning_content, ignored here).

SARVAM_PREFIX = "sarvam/"
SARVAM_DEFAULT_BASE_URL = "https://api.sarvam.ai/v2"
SARVAM_DEFAULT_MAX_TOKENS = 32768

# Multimodal Sarvam models get the page images, like Gemini, instead of an OCR transcript.
# Gemma 4 31B ("gemma4") is the only one at the time of writing; SARVAM_VISION_MODELS
# (comma-separated model names) overrides the list. Sarvam accepts images only as base64
# data URIs (remote URLs are rejected) and caps a request body at 10 MB, so the images are
# re-encoded as JPEG and shrunk until they fit SARVAM_IMAGE_BUDGET_MB.
SARVAM_DEFAULT_VISION_MODELS = ("gemma4",)
SARVAM_DEFAULT_IMAGE_BUDGET_MB = 8.0
SARVAM_DEFAULT_IMAGE_MAX_SIDE = 1600


def _sarvam_config():
    key = os.getenv("SARVAM_API_KEY", "").strip()
    if not key:
        raise EvaluationError("SARVAM_API_KEY is not configured on the server.")
    base = (os.getenv("SARVAM_BASE_URL") or SARVAM_DEFAULT_BASE_URL).rstrip("/")
    try:
        max_tokens = int(os.getenv("SARVAM_MAX_TOKENS") or SARVAM_DEFAULT_MAX_TOKENS)
    except ValueError:
        max_tokens = SARVAM_DEFAULT_MAX_TOKENS
    return key, base, max_tokens


def _without_think(tokens):
    """Drop <think>…</think> blocks some providers put inline in the content."""
    buf, thinking = "", False
    for token in tokens:
        buf += token
        while True:
            if thinking:
                end = buf.find("</think>")
                if end < 0:
                    buf = buf[-8:]
                    break
                buf, thinking = buf[end + 8:], False
            else:
                start = buf.find("<think>")
                if start < 0:
                    keep = max(0, len(buf) - 7)  # a tag may be split across chunks
                    if keep:
                        yield buf[:keep]
                        buf = buf[keep:]
                    break
                if start:
                    yield buf[:start]
                buf, thinking = buf[start + 7:], True
    if buf and not thinking:
        yield buf


def _sarvam_tokens(model_code, system_prompt, user_content):
    """Stream a Sarvam chat completion and yield the answer's text (not its reasoning).

    ``user_content`` is a string, or a list of OpenAI-style content parts for vision models.
    """
    import httpx

    key, base, max_tokens = _sarvam_config()
    body = {
        "model": model_code.removeprefix(SARVAM_PREFIX),
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    headers = {"api-subscription-key": key, "Content-Type": "application/json", "Accept": "text/event-stream"}
    timeout = httpx.Timeout(connect=20.0, read=float(os.getenv("SARVAM_READ_TIMEOUT") or 300), write=60.0, pool=20.0)

    def content():
        with httpx.stream("POST", f"{base}/chat/completions", json=body, headers=headers, timeout=timeout) as response:
            if response.status_code >= 400:
                detail = response.read().decode("utf-8", "replace")
                try:
                    payload = json.loads(detail)
                    error = payload.get("error", payload)
                    detail = error.get("message") if isinstance(error, dict) else str(error)
                except ValueError:
                    pass
                if response.status_code in (401, 403):
                    raise EvaluationError(f"Sarvam rejected the API key (HTTP {response.status_code}): {_text(detail, 300)}")
                if response.status_code == 413:
                    raise EvaluationError("The request is larger than Sarvam accepts (10 MB). Lower SARVAM_IMAGE_BUDGET_MB "
                                          "or evaluate fewer pages at a time.")
                if response.status_code == 429:
                    raise EvaluationError(f"Sarvam rate limit reached (HTTP 429). Wait a minute and try again: {_text(detail, 200)}")
                raise EvaluationError(f"Sarvam API error (HTTP {response.status_code}): {_text(detail, 300)}")
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                if chunk.get("error"):
                    error = chunk["error"]
                    raise EvaluationError(f"Sarvam error: {_text(error.get('message') if isinstance(error, dict) else error, 300)}")
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        yield delta["content"]

    return _without_think(content())


def _stream_sarvam_evaluation(pages, model_code, reference_urls, instructions, max_marks, log_context,
                              transcript=None):
    _sarvam_config()  # fail fast, before any OCR, when the key is missing
    try:
        if not transcript:
            transcript = yield from ocr_pages(pages, log_context)
        if reference_urls and transcript.get("reference_texts") is None:
            yield {"kind": "status", "text": f"Reading the question paper / answer key with {transcript_engine_name()}…"}
        transcript = {**transcript, "reference_texts": kept_reference_texts(transcript, reference_urls, log_context)}
        yield {"kind": "transcript", "transcript": transcript}
        reference = reference_text(reference_urls, texts=transcript["reference_texts"]) if reference_urls else ""
        index = LineIndex(transcript)
        sizes = {p["number"]: (p["width"], p["height"]) for p in transcript["pages"]}
        yield {"kind": "status", "text": f"{model_code.removeprefix(SARVAM_PREFIX)} is evaluating…"}
        reply = _Reply(_sarvam_tokens(model_code, build_evaluation_prompt(max_marks, mode="text"),
                                      build_text_user_content(transcript, reference, instructions)))
        normalizer = EvaluationNormalizer(sizes, max_marks)
        read = 0
        for raw in settle_answers(iter_json_objects(reply)):
            item = normalizer.add(resolve_lines(raw, index, sizes))
            if item:
                read += 1
                yield item
        check_readable(reply, read, model_code)
    except EvaluationError:
        raise
    except Exception as e:
        log_and_raise(e, model_code=model_code, provider="sarvam", log_context=log_context,
                      custom_message=f"Sarvam evaluation error: {e}")


def _stream_sarvam_reevaluation(pages, model_code, revision, reference_urls, instructions, max_marks, log_context):
    _sarvam_config()
    try:
        transcript = revision.transcript
        if not transcript:
            transcript = yield from ocr_pages(pages, log_context)
            yield {"kind": "transcript", "transcript": transcript}
        texts = kept_reference_texts(transcript, reference_urls, log_context)
        reference = reference_text(reference_urls, texts=texts) if reference_urls else ""
        index = LineIndex(transcript)
        sizes = {p["number"]: (p["width"], p["height"]) for p in transcript["pages"]}
        user = build_text_user_content(transcript, reference, instructions)
        user += "\n\nPREVIOUS EVALUATION:\n" + json.dumps(to_text_model_format(revision.previous, index), ensure_ascii=False)
        history = [h for h in revision.history if h.get("feedback")][-MAX_HISTORY_TURNS:]
        if history:
            user += "\n\nEARLIER FEEDBACK (already applied):\n" + "\n".join(
                f"- Teacher: {_text(h['feedback'], 500)}\n  You replied: {_text(h.get('reply'), 500)}" for h in history)
        user += "\n\n" + _feedback_block(revision)
        reply = _Reply(_sarvam_tokens(model_code, build_revision_prompt(max_marks, revision, mode="text"), user))
        read = 0
        for item in revise_objects((resolve_lines(raw, index, sizes) for raw in settle_answers(iter_json_objects(reply))),
                                   sizes, max_marks, revision):
            read += 1
            yield item
        check_readable(reply, read, model_code)
    except EvaluationError:
        raise
    except Exception as e:
        log_and_raise(e, model_code=model_code, provider="sarvam", log_context=log_context,
                      custom_message=f"Sarvam re-evaluation error: {e}")


def sarvam_vision_models():
    configured = os.getenv("SARVAM_VISION_MODELS")
    names = configured.split(",") if configured is not None else SARVAM_DEFAULT_VISION_MODELS
    return {name.strip() for name in names if name.strip()}


def _is_sarvam_vision(model_code):
    return _is_sarvam(model_code) and model_code.removeprefix(SARVAM_PREFIX) in sarvam_vision_models()


def _env_number(name, default, cast=float):
    try:
        value = cast(os.getenv(name) or default)
    except ValueError:
        return default
    return value if value > 0 else default


def _fetch_image(url):
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return ImageOps.exif_transpose(PILImage.open(io.BytesIO(response.content))).convert("RGB")


def _jpeg_data_url(img, max_side, quality):
    scale = min(1.0, max_side / max(img.size))
    if scale < 1.0:
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), PILImage.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def encode_images_within_budget(images, budget_bytes, max_side=SARVAM_DEFAULT_IMAGE_MAX_SIDE):
    """JPEG data URIs for the images, shrinking resolution then quality until all of them
    together fit ``budget_bytes``. Boxes are normalised (0-1000), so resizing does not
    change them. Returns (data URIs, total bytes)."""
    total = 0
    for scale, quality in ((1.0, 85), (1.0, 72), (0.8, 72), (0.65, 68), (0.5, 62), (0.4, 55)):
        urls = [_jpeg_data_url(img, int(max_side * scale), quality) for img in images]
        total = sum(len(u) for u in urls)
        if total <= budget_bytes:
            return urls, total
    raise EvaluationError(
        f"The {len(images)} images are too large to send to Sarvam even after shrinking them "
        f"({total / 1e6:.1f} MB; a request is limited to 10 MB). Evaluate fewer pages at a time.")


def _sarvam_vision_images(pages, reference_urls):
    """(sheet data URIs, reference data URIs, total bytes); fills in missing page sizes."""
    sheet = []
    for page in pages:
        img = _fetch_image(page.url)
        if not (page.width and page.height):
            page.width, page.height = img.size
        sheet.append(img)
    references = [_fetch_image(url) for url in list(reference_urls)[:MAX_REFERENCE_PAGES]]
    budget = _env_number("SARVAM_IMAGE_BUDGET_MB", SARVAM_DEFAULT_IMAGE_BUDGET_MB) * 1024 * 1024
    max_side = _env_number("SARVAM_IMAGE_MAX_SIDE", SARVAM_DEFAULT_IMAGE_MAX_SIDE, int)
    urls, total = encode_images_within_budget(sheet + references, budget, max_side)
    return urls[:len(sheet)], urls[len(sheet):], total


def vision_with_ocr():
    """Whether vision models also get OCR blocks: EVAL_VISION_WITH_OCR=on/off, by default on
    when Bodhan's OCR is configured."""
    choice = (os.getenv("EVAL_VISION_WITH_OCR") or "auto").strip().lower()
    if choice in ("off", "0", "false", "no"):
        return False
    return choice in ("on", "1", "true", "yes") or bodhan_ocr_configured()


def _stream_sarvam_hybrid_evaluation(pages, model_code, reference_urls, instructions, max_marks, log_context,
                                     transcript=None):
    _sarvam_config()
    name = model_code.removeprefix(SARVAM_PREFIX)
    try:
        if not transcript:
            transcript = yield from ocr_pages(pages, log_context)
        if reference_urls and transcript.get("reference_texts") is None:
            yield {"kind": "status", "text": f"Reading the question paper / answer key with {transcript_engine_name()}…"}
        reference_texts = kept_reference_texts(transcript, reference_urls, log_context)
        transcript = {**transcript, "reference_texts": reference_texts}
        yield {"kind": "transcript", "transcript": transcript}
        sheet, references, total = _sarvam_vision_images(pages, reference_urls)
        blocks = sum(len(p["lines"]) for p in transcript["pages"])
        yield {"kind": "status", "text": f"{name} is reading {len(pages)} page image(s) ({total / 1e6:.1f} MB) "
                                         f"with {blocks} OCR blocks and evaluating…"}
        index = LineIndex(transcript)
        sizes = page_sizes_of(pages)
        content = build_hybrid_user_content([(p.number, u) for p, u in zip(pages, sheet)], transcript,
                                            references, reference_texts, instructions)
        content.append({"type": "text", "text": EVALUATE_REQUEST})
        reply = _Reply(_sarvam_tokens(model_code, build_evaluation_prompt(max_marks, mode="hybrid"), content))
        normalizer = EvaluationNormalizer(sizes, max_marks)
        resolver = HybridResolver(index, sizes)
        read = 0
        for raw in settle_answers(iter_json_objects(reply)):
            item = normalizer.add(resolver.resolve(raw))
            if item:
                read += 1
                yield item
        check_readable(reply, read, model_code)
    except EvaluationError:
        raise
    except Exception as e:
        log_and_raise(e, model_code=model_code, provider="sarvam", log_context=log_context,
                      custom_message=f"Sarvam evaluation error: {e}")


def _stream_sarvam_hybrid_reevaluation(pages, total_pages, page_sizes, model_code, revision, reference_urls,
                                       instructions, max_marks, log_context, all_pages):
    _sarvam_config()
    name = model_code.removeprefix(SARVAM_PREFIX)
    try:
        transcript = revision.transcript
        if not transcript:
            transcript = yield from ocr_pages(all_pages, log_context)
            yield {"kind": "transcript", "transcript": transcript}
        yield {"kind": "status", "text": f"{name} is re-reading page(s) {', '.join(str(p.number) for p in pages)}…"}
        reference_texts = kept_reference_texts(transcript, reference_urls, log_context)
        sheet, references, _ = _sarvam_vision_images(pages, reference_urls)
        index = LineIndex(transcript)
        needed = {p.number for p in pages}
        content = build_hybrid_user_content(
            [(p.number, u) for p, u in zip(pages, sheet)],
            {"pages": [p for p in transcript["pages"] if p["number"] in needed] or transcript["pages"]},
            references, reference_texts, instructions)
        content.append({"type": "text", "text": "PREVIOUS EVALUATION:\n" + json.dumps(
            to_hybrid_model_format(revision.previous, index, page_sizes), ensure_ascii=False)})
        history = [h for h in revision.history if h.get("feedback")][-MAX_HISTORY_TURNS:]
        if history:
            content.append({"type": "text", "text": "EARLIER FEEDBACK (already applied):\n" + "\n".join(
                f"- Teacher: {_text(h['feedback'], 500)}\n  You replied: {_text(h.get('reply'), 500)}" for h in history)})
        content.append({"type": "text", "text": _feedback_block(revision)})
        reply = _Reply(_sarvam_tokens(model_code, build_revision_prompt(max_marks, revision, mode="hybrid"), content))
        resolver = HybridResolver(index, page_sizes)
        read = 0
        for item in revise_objects((resolver.resolve(raw) for raw in settle_answers(iter_json_objects(reply))),
                                   page_sizes, max_marks, revision):
            read += 1
            yield item
        check_readable(reply, read, model_code)
    except EvaluationError:
        raise
    except Exception as e:
        log_and_raise(e, model_code=model_code, provider="sarvam", log_context=log_context,
                      custom_message=f"Sarvam re-evaluation error: {e}")


def _stream_sarvam_vision_evaluation(pages, model_code, reference_urls, instructions, max_marks, log_context):
    _sarvam_config()  # fail fast when the key is missing
    name = model_code.removeprefix(SARVAM_PREFIX)
    try:
        yield {"kind": "status", "text": f"Preparing {len(pages)} page image(s) for {name}…"}
        sheet, references, total = _sarvam_vision_images(pages, reference_urls)
        yield {"kind": "status", "text": f"{name} is reading {len(pages)} page(s) "
                                         f"({total / 1e6:.1f} MB of images) and evaluating…"}
        loaded = [(page.number, url) for page, url in zip(pages, sheet)]
        reply = _Reply(_sarvam_tokens(model_code, build_evaluation_prompt(max_marks, mode="image"),
                                      build_user_content(loaded, len(pages), references, instructions)))
        normalizer = EvaluationNormalizer(page_sizes_of(pages), max_marks)
        read = 0
        for raw in settle_answers(iter_json_objects(reply)):
            item = normalizer.add(raw)
            if item:
                read += 1
                yield item
        check_readable(reply, read, model_code)
    except EvaluationError:
        raise
    except Exception as e:
        log_and_raise(e, model_code=model_code, provider="sarvam", log_context=log_context,
                      custom_message=f"Sarvam evaluation error: {e}")


def _stream_sarvam_vision_reevaluation(pages, total_pages, page_sizes, model_code, revision, reference_urls,
                                       instructions, max_marks, log_context):
    _sarvam_config()
    name = model_code.removeprefix(SARVAM_PREFIX)
    try:
        yield {"kind": "status", "text": f"{name} is re-reading page(s) {', '.join(str(p.number) for p in pages)}…"}
        sheet, references, _ = _sarvam_vision_images(pages, reference_urls)
        loaded = [(page.number, url) for page, url in zip(pages, sheet)]
        content = build_revision_content(loaded, total_pages, references, instructions,
                                         to_model_format(revision.previous, page_sizes), revision)
        reply = _Reply(_sarvam_tokens(model_code, build_revision_prompt(max_marks, revision, mode="image"), content))
        read = 0
        for item in revise_objects(settle_answers(iter_json_objects(reply)), page_sizes, max_marks, revision):
            read += 1
            yield item
        check_readable(reply, read, model_code)
    except EvaluationError:
        raise
    except Exception as e:
        log_and_raise(e, model_code=model_code, provider="sarvam", log_context=log_context,
                      custom_message=f"Sarvam re-evaluation error: {e}")


# ── Gemini ───────────────────────────────────────────────────────────────────

def _gemini_api_key():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EvaluationError("GOOGLE_API_KEY is not configured on the server.")
    return api_key


def _gemini_tokens(api_key, model_code, system_prompt, user_content):
    client = OpenAI(api_key=api_key, base_url=GEMINI_BASE_URL)
    stream = client.chat.completions.create(
        model=model_code.removeprefix(GEMINI_PREFIX),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        stream=True,
    )
    return (chunk.choices[0].delta.content or "" for chunk in stream if chunk.choices)


def _stream_gemini_evaluation(pages, model_code, reference_urls, instructions, max_marks, log_context):
    api_key = _gemini_api_key()
    try:
        loaded = _load_pages(pages)
        reference_data = [_load_image(url)[0] for url in list(reference_urls)[:MAX_REFERENCE_PAGES]]
        reply = _Reply(_gemini_tokens(api_key, model_code, build_evaluation_prompt(max_marks),
                                      build_user_content(loaded, len(pages), reference_data, instructions)))
        normalizer = EvaluationNormalizer(page_sizes_of(pages), max_marks)
        read = 0
        for raw in settle_answers(iter_json_objects(reply)):
            item = normalizer.add(raw)
            if item:
                read += 1
                yield item
        check_readable(reply, read, model_code)
    except EvaluationError:
        raise
    except Exception as e:
        log_and_raise(e, model_code=model_code, provider="google", log_context=log_context,
                      custom_message=f"Gemini evaluation error: {e}")


def _stream_gemini_reevaluation(pages, total_pages, page_sizes, model_code, revision, reference_urls,
                                instructions, max_marks, log_context):
    api_key = _gemini_api_key()
    try:
        loaded = _load_pages(pages)
        reference_data = [_load_image(url)[0] for url in list(reference_urls)[:MAX_REFERENCE_PAGES]]
        content = build_revision_content(loaded, total_pages, reference_data, instructions,
                                         to_model_format(revision.previous, page_sizes), revision)
        reply = _Reply(_gemini_tokens(api_key, model_code, build_revision_prompt(max_marks, revision), content))
        read = 0
        for item in revise_objects(settle_answers(iter_json_objects(reply)), page_sizes, max_marks, revision):
            read += 1
            yield item
        check_readable(reply, read, model_code)
    except EvaluationError:
        raise
    except Exception as e:
        log_and_raise(e, model_code=model_code, provider="google", log_context=log_context,
                      custom_message=f"Gemini re-evaluation error: {e}")


def _is_gemini(model_code):
    return model_code.startswith(GEMINI_PREFIX) or model_code.startswith("gemini")


def _is_sarvam(model_code):
    return model_code.startswith(SARVAM_PREFIX)


def check_pages(pages):
    if not pages:
        raise EvaluationError("The answer sheet has no pages.")
    if len(pages) > MAX_DOCUMENT_PAGES:
        raise EvaluationError(f"Answer sheets can have at most {MAX_DOCUMENT_PAGES} pages.")


def check_revision(pages, revision):
    check_pages(pages)
    if revision.scope not in REVISION_SCOPES:
        raise EvaluationError(f"Unknown scope '{revision.scope}'.")
    if revision.scope == "answer" and revision.target is None:
        raise EvaluationError("That answer is no longer on this sheet.")
    if revision.scope == "page" and not (revision.page and 1 <= revision.page <= len(pages)):
        raise EvaluationError("That page is not part of this answer sheet.")


def stream_evaluation(pages, model_code, reference_urls=(), instructions="",
                      max_marks=None, log_context=None, transcript=None):
    """Generator of normalized answer/finding annotations for a whole answer sheet.

    ``pages`` is the list of SheetPage, numbered from 1, in order. Besides annotations it
    may yield {"kind": "status", "text"} progress notes and, for text-only models, one
    {"kind": "transcript", "transcript"} with the OCR transcript to keep for revisions
    (``transcript`` passes a kept one back in, skipping the OCR).
    """
    check_pages(pages)
    max_marks = marks_setting(max_marks)
    if _is_gemini(model_code):
        return _stream_gemini_evaluation(pages, model_code, reference_urls, instructions,
                                         max_marks, log_context)
    if _is_sarvam_vision(model_code):
        if vision_with_ocr():
            return _stream_sarvam_hybrid_evaluation(pages, model_code, reference_urls, instructions,
                                                    max_marks, log_context, transcript)
        return _stream_sarvam_vision_evaluation(pages, model_code, reference_urls, instructions,
                                                max_marks, log_context)
    if _is_sarvam(model_code):
        return _stream_sarvam_evaluation(pages, model_code, reference_urls, instructions,
                                         max_marks, log_context, transcript)
    raise EvaluationError(f"No evaluation backend for model '{model_code}'.")


def stream_reevaluation(pages, model_code, revision, reference_urls=(), instructions="",
                        max_marks=None, log_context=None):
    """Generator of a {"kind": "reply"} dict followed by the revised annotations.

    ``pages`` is every SheetPage of the sheet; only those the revision needs are sent.
    """
    check_revision(pages, revision)
    max_marks = marks_setting(max_marks)
    if _is_sarvam_vision(model_code) and (revision.transcript or vision_with_ocr()):
        needed = set(revision.pages_needed(len(pages)))
        return _stream_sarvam_hybrid_reevaluation([p for p in pages if p.number in needed], len(pages),
                                                  page_sizes_of(pages), model_code, revision, reference_urls,
                                                  instructions, max_marks, log_context, pages)
    if _is_sarvam_vision(model_code):
        needed = set(revision.pages_needed(len(pages)))
        return _stream_sarvam_vision_reevaluation([p for p in pages if p.number in needed], len(pages),
                                                  page_sizes_of(pages), model_code, revision, reference_urls,
                                                  instructions, max_marks, log_context)
    if _is_sarvam(model_code):
        return _stream_sarvam_reevaluation(pages, model_code, revision, reference_urls, instructions,
                                           max_marks, log_context)
    if _is_gemini(model_code):
        needed = set(revision.pages_needed(len(pages)))
        return _stream_gemini_reevaluation([p for p in pages if p.number in needed], len(pages),
                                           page_sizes_of(pages), model_code, revision, reference_urls,
                                           instructions, max_marks, log_context)
    raise EvaluationError(f"No evaluation backend for model '{model_code}'.")
