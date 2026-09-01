"""PDF extractor — OCR (AR+EN) + optional Vision-LLM hook.

Strategy for MVP:
  1. Convert PDF pages to images (pdf2image / poppler).
  2. OCR each page with Tesseract (`ara+eng`).
  3. Light heuristic detection of keywords (door schedule, window schedule, table totals).
  4. If OPENAI_API_KEY is set → call Vision-LLM with each page to identify elements
     with bounding boxes (delegated to a small helper that returns structured JSON).
  5. Confidence per element starts at 0.6 from OCR heuristics, 0.75 from vision.

The Vision-LLM call is intentionally guarded so the platform works end-to-end
without external keys (deterministic OCR-only path).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pdf2image import convert_from_path
import pytesseract

from app.core.config import settings


@dataclass
class ExtractedPdfElement:
    element_type: str
    discipline: str | None
    geometry: dict[str, Any] = field(default_factory=dict)
    source_ref: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.6
    extraction_method: str = "ocr"


# Heuristic keyword → (element_type, discipline, default geometry field)
# These are intentionally conservative — they only fire when the text is very obvious.
_DOOR_RE = re.compile(r"\b(door|باب|أبواب)\b[^\n]{0,40}?(\d{1,3})", re.IGNORECASE)
_WINDOW_RE = re.compile(r"\b(window|نافذة|نوافذ|شباك)\b[^\n]{0,40}?(\d{1,3})", re.IGNORECASE)
# Concrete volume table: "خرسانة ... 142.5 م3" or "concrete ... 142.5 m3"
_CONCRETE_RE = re.compile(
    r"(concrete|خرسانة)[^\n]{0,60}?(\d{1,6}(?:\.\d+)?)\s*(?:m3|م3|م³)",
    re.IGNORECASE,
)
_REBAR_RE = re.compile(
    r"(rebar|steel|حديد)[^\n]{0,60}?(\d{1,6}(?:\.\d+)?)\s*(?:ton|طن)",
    re.IGNORECASE,
)
_BLOCK_RE = re.compile(
    r"(block|بلوك|مباني)[^\n]{0,60}?(\d{1,6}(?:\.\d+)?)\s*(?:m2|م2|م²)",
    re.IGNORECASE,
)


def _ocr_page(image, page_no: int) -> tuple[str, dict]:
    """Returns (full_text, layout) where layout has token positions for provenance."""
    text = pytesseract.image_to_string(image, lang="ara+eng")
    data = pytesseract.image_to_data(image, lang="ara+eng", output_type=pytesseract.Output.DICT)
    return text, data


def _heuristic_elements(text: str, page_no: int) -> list[ExtractedPdfElement]:
    out: list[ExtractedPdfElement] = []

    def _add(kind: str, discipline: str, count: int | None = None, qty: float | None = None,
             unit_field: str = "count"):
        geom: dict[str, Any] = {}
        if unit_field == "count" and count is not None:
            # emit `count` separate elements so aggregator can count them.
            for _ in range(min(count, 999)):
                out.append(
                    ExtractedPdfElement(
                        element_type=kind,
                        discipline=discipline,
                        geometry={"count": 1},
                        source_ref={"page": page_no, "method": "ocr_keyword"},
                        confidence=0.6,
                    )
                )
        elif qty is not None:
            geom[unit_field] = qty
            out.append(
                ExtractedPdfElement(
                    element_type=kind,
                    discipline=discipline,
                    geometry=geom,
                    source_ref={"page": page_no, "method": "ocr_keyword"},
                    confidence=0.6,
                )
            )

    for m in _DOOR_RE.finditer(text):
        try:
            _add("door", "arch", count=int(m.group(2)))
        except ValueError:
            continue
    for m in _WINDOW_RE.finditer(text):
        try:
            _add("window", "arch", count=int(m.group(2)))
        except ValueError:
            continue
    for m in _CONCRETE_RE.finditer(text):
        try:
            _add("slab", "struct", qty=float(m.group(2)), unit_field="volume_m3")
        except ValueError:
            continue
    for m in _BLOCK_RE.finditer(text):
        try:
            _add("wall", "arch", qty=float(m.group(2)), unit_field="area_m2")
        except ValueError:
            continue
    return out


def _vision_llm_elements(image, page_no: int) -> list[ExtractedPdfElement]:
    """Optional path: call GPT-4o-Vision to identify quantifiable elements.

    Returns [] silently if the API key is not configured or call fails — this keeps
    the pipeline deterministic in dev. In production the operator wires real keys.
    """
    if not settings.openai_api_key:
        return []
    try:
        import base64
        import io
        import httpx
    except Exception:
        return []

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    prompt = (
        "You are an expert quantity surveyor. Analyse this construction drawing page "
        "and return ONLY a JSON object: {\"elements\":[{\"type\":\"wall|slab|column|"
        "beam|footing|door|window|space|cable|pipe|hvac_unit\",\"qty\":<number>,"
        "\"unit_field\":\"area_m2|volume_m3|length_m|count\",\"bbox\":[x,y,w,h],"
        "\"confidence\":0..1}]}. Use the drawing scale and dimensions visible. "
        "If unsure, omit the element. No prose."
    )
    payload = {
        "model": settings.vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    try:
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json=payload,
            timeout=120,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
    except Exception:
        return []

    out: list[ExtractedPdfElement] = []
    for e in data.get("elements", []):
        et = e.get("type")
        qty = e.get("qty")
        unit_field = e.get("unit_field", "count")
        if not et or qty is None:
            continue
        out.append(
            ExtractedPdfElement(
                element_type=et,
                discipline=None,
                geometry={unit_field: float(qty)} if unit_field != "count" else {"count": int(qty)},
                source_ref={"page": page_no, "bbox": e.get("bbox"), "method": "vision_llm"},
                confidence=float(e.get("confidence", 0.75)),
                extraction_method="vision_llm",
            )
        )
    return out


def extract_elements(pdf_path: str, *, max_pages: int = 30) -> tuple[list[ExtractedPdfElement], int]:
    """Returns (elements, total_pages)."""
    images = convert_from_path(pdf_path, dpi=180, first_page=1, last_page=max_pages)
    total = len(images)
    all_elements: list[ExtractedPdfElement] = []
    for i, img in enumerate(images, start=1):
        text, _layout = _ocr_page(img, i)
        all_elements.extend(_heuristic_elements(text, i))
        all_elements.extend(_vision_llm_elements(img, i))
    return all_elements, total
