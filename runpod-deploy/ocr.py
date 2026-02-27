#!/usr/bin/env python3
"""OCR d'un fichier PDF ou d'une image via vLLM déployé sur RunPod.

Formats de sortie :
  - text  : texte brut extrait (défaut)
  - json  : tableau JSON avec texte + bounding boxes par chunk détecté

Usage :
  python ocr.py photo.jpg
  python ocr.py photo.jpg --model chandra
  python ocr.py document.pdf --pages 1-3 --format json -o result.json
"""

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


# ── Backends ─────────────────────────────────────────────────

BACKENDS: dict[str, dict] = {
    "qwen3":   {"env_var": "QWEN3VL_POD_ID",  "model_name": "qwen3-vl", "repetition_penalty": 1.15, "max_tokens": 8192},
    "chandra": {"env_var": "CHANDRA_POD_ID",   "model_name": "chandra",  "repetition_penalty": 1.15, "max_tokens": 8192},
}


# ── PDF helpers ──────────────────────────────────────────────

def get_page_count(pdf_path: str) -> int:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf_path)
    count = len(doc)
    doc.close()
    return count


def pdf_page_to_base64png(pdf_path: str, page_index: int) -> str:
    """Render a PDF page to a base64 PNG string (0-indexed)."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf_path)
    page = doc[page_index]
    # Render at 2x for good quality (default is 72 dpi → 144 dpi)
    bitmap = page.render(scale=2)
    pil_image = bitmap.to_pil()
    doc.close()

    import io
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ── Image helper ─────────────────────────────────────────────

def image_to_base64(image_path: str) -> tuple[str, str]:
    """Read an image file and return (base64_data, mime_type)."""
    path = Path(image_path)
    suffix = path.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
    }
    mime = mime_map.get(suffix, "image/jpeg")
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return data, mime


# ── Page range parsing ───────────────────────────────────────

def parse_page_range(spec: str, total: int) -> list[int]:
    """Parse '3', '1-5', or '2,4,7-9' into a sorted list of 1-based page numbers."""
    pages = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            start, end = int(start), int(end)
            pages.update(range(start, min(end, total) + 1))
        else:
            p = int(part)
            if 1 <= p <= total:
                pages.add(p)
    return sorted(pages)


# ── Fill-zone normalization ──────────────────────────────────

# Collapse runs of 4+ repeated dots, dashes, or underscores into a placeholder.
# This handles form fill-in zones that cause models to loop.
_FILL_RE = re.compile(r'([.\-_])\1{3,}')

def normalize_fill_zones(text: str) -> str:
    return _FILL_RE.sub('___', text)


# ── Prompts ──────────────────────────────────────────────────

_FILL_ZONE_RULE = (
    # "Sequences of repeated dots, underscores, or dashes used as fill-in zones "
    # "(e.g. '............', '_ _ _ _', '----------') must be represented as a "
    # 'single "___" placeholder — do not transcribe each character individually.'
    # "Do not repeat dots more than three times. They represent fill zones and you must discard them"
    "Ignore dotted lines. Only transcribe actual alphanumeric text."
)

PROMPT_TEXT_ONLY = (
    "Extract all the alphanumeric text from this image. Return plain text only, "
    "preserving the reading order."
    "Ignore dotted lines. Ignore ".....". Only transcribe actual alphanumeric text."
    "Do NOT use HTML tags, XML, or any markup — plain text only. "
    "Do not describe the image, just return the extracted text. "
)

PROMPT_HTML = (
    "Extract all the alphanumeric text from this image and return it as clean HTML. "
    "Use semantic tags: <h1>–<h4> for headings, <p> for paragraphs, "
    "<table>/<tr>/<th>/<td> for tables, <ul>/<li> for lists. "
    "Preserve reading order and document structure. "
    "Return ONLY the HTML body content, no <html>/<head>/<body> wrapper. "
    + _FILL_ZONE_RULE
)

PROMPT_BBOX_JSON = (
    "Perform OCR on this image. Return a JSON array where each element corresponds "
    "to one visually distinct text chunk — a group of characters that are close "
    "together and separated from neighbouring text by a visible gap. "
    "A single visual line may contain several independent chunks (e.g. a label on "
    "the left and a value on the right of the same row); each must be its own entry. "
    "Never merge text from different chunks into one entry, and never split a "
    "continuous block of characters into multiple entries. "
    + _FILL_ZONE_RULE + "\n"
    "Each element must have:\n"
    '  - "text": the extracted text of that chunk\n'
    '  - "bbox": [x, y, w, h] where x,y are the top-left corner coordinates and '
    "w,h are width and height, all as relative values between 0.0 and 1.0 "
    "(proportional to image dimensions)\n\n"
    "Return ONLY the JSON array, no explanation, no markdown fences."
)


# ── API call ─────────────────────────────────────────────────

def ocr_image_base64(
    client: OpenAI,
    model: str,
    img_base64: str,
    mime_type: str,
    output_format: str,
    repetition_penalty: float = 1.15,
    max_tokens: int = 8192,
) -> str:
    """Send a single image to the OCR model and return the raw response text."""
    prompt = {"json": PROMPT_BBOX_JSON, "html": PROMPT_HTML}.get(output_format, PROMPT_TEXT_ONLY)

    # Stream the response to keep the connection alive through Cloudflare's
    # 100s proxy timeout (HTTP 524 occurs with non-streaming long inference).
    stream = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{img_base64}",
                        },
                    },
                ],
            }
        ],
        temperature=0.0,
        max_tokens=max_tokens,
        extra_body={"repetition_penalty": repetition_penalty},
        stream=True,
    )
    parts: list[str] = []
    finish_reason: str | None = None
    for chunk in stream:
        choice = chunk.choices[0] if chunk.choices else None
        if choice is None:
            continue
        if choice.delta.content:
            parts.append(choice.delta.content)
        if choice.finish_reason:
            finish_reason = choice.finish_reason
    if finish_reason == "length":
        print(f"  ⚠️  finish_reason=length — réponse tronquée, augmenter max_tokens ({max_tokens})",
              file=sys.stderr)
    return "".join(parts)


# ── JSON post-processing ────────────────────────────────────

def parse_bbox_response(raw: str) -> list[dict]:
    """Try to parse the model's bbox JSON response, tolerating markdown fences."""
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (fences)
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            # Guard against [{"text": "<json array string>"}] wrapper
            if (len(data) == 1 and isinstance(data[0], dict)
                    and "text" in data[0] and "bbox" not in data[0]):
                inner = data[0]["text"]
                if isinstance(inner, str):
                    try:
                        parsed = json.loads(inner)
                        if isinstance(parsed, list):
                            return parsed
                    except json.JSONDecodeError:
                        pass
            return data
        # Model returned a bare dict — check if "text" field contains the actual array
        if isinstance(data, dict) and "text" in data:
            inner = data["text"]
            if isinstance(inner, list):
                return inner
            if isinstance(inner, str):
                try:
                    parsed = json.loads(inner)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
        return [data]
    except json.JSONDecodeError:
        # Last resort: try to extract a JSON array anywhere in the response
        import re
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return [{"text": raw, "bbox": None, "parse_error": True}]


# ── Main ─────────────────────────────────────────────────────

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="OCR d'un PDF ou image via vLLM sur RunPod"
    )
    parser.add_argument("input", help="Chemin vers le fichier (PDF, JPEG, PNG...)")
    parser.add_argument(
        "--model", choices=list(BACKENDS), default="qwen3",
        help="Modèle à utiliser : qwen3 (défaut) ou chandra",
    )
    parser.add_argument(
        "--pages", default=None,
        help="Pages à traiter (PDF uniquement) : 3, 1-5, 2,4,7-9 (défaut : toutes)",
    )
    parser.add_argument(
        "--format", dest="output_format", choices=["text", "html", "json"], default="text",
        help="Format de sortie : text (défaut), html, ou json (texte + bounding boxes)",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Fichier de sortie (défaut : stdout)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Erreur : fichier introuvable : {input_path}", file=sys.stderr)
        sys.exit(1)

    backend = BACKENDS[args.model]
    pod_id = os.environ.get(backend["env_var"])
    if not pod_id:
        print(
            f"Erreur : {backend['env_var']} manquant dans .env",
            file=sys.stderr,
        )
        sys.exit(1)

    model_name = backend["model_name"]
    base_url = f"https://{pod_id}-8000.proxy.runpod.net/v1"
    client = OpenAI(base_url=base_url, api_key="not-needed")
    print(f"Backend : {args.model} ({model_name})", file=sys.stderr)

    is_pdf = input_path.suffix.lower() == ".pdf"

    # Build list of (base64_data, mime_type, page_label) tuples
    images: list[tuple[str, str, str]] = []

    if is_pdf:
        total_pages = get_page_count(str(input_path))
        if args.pages:
            page_nums = parse_page_range(args.pages, total_pages)
        else:
            page_nums = list(range(1, total_pages + 1))
        print(
            f"PDF : {input_path.name} — {total_pages} page(s), "
            f"traitement de {len(page_nums)} page(s)",
            file=sys.stderr,
        )
        for pn in page_nums:
            b64 = pdf_page_to_base64png(str(input_path), pn - 1)
            images.append((b64, "image/png", f"page {pn}"))
    else:
        b64, mime = image_to_base64(str(input_path))
        images.append((b64, mime, input_path.name))
        print(f"Image : {input_path.name}", file=sys.stderr)

    # Process each image
    all_text_results: list[str] = []
    all_json_results: list[dict] = []

    for img_b64, mime, label in images:
        print(f"  {label}...", file=sys.stderr, end=" ", flush=True)
        raw = ocr_image_base64(
            client, model_name, img_b64, mime, args.output_format,
            repetition_penalty=backend["repetition_penalty"],
            max_tokens=backend["max_tokens"],
        )
        print("OK", file=sys.stderr)

        if args.output_format == "json":
            regions = parse_bbox_response(raw)
            for r in regions:
                if isinstance(r.get("text"), str):
                    r["text"] = normalize_fill_zones(r["text"])
            all_json_results.append({"source": label, "regions": regions})
        elif args.output_format == "text":
            # Safety net: strip HTML tags if the model returned markup anyway
            cleaned = re.sub(r"<[^>]+>", " ", raw)
            cleaned = re.sub(r" {2,}", " ", cleaned).strip()
            all_text_results.append(normalize_fill_zones(cleaned))
        else:  # html
            all_text_results.append(normalize_fill_zones(raw))

    # Format output
    if args.output_format == "json":
        # Flatten if single image
        if len(all_json_results) == 1:
            output = json.dumps(all_json_results[0]["regions"], indent=2, ensure_ascii=False)
        else:
            output = json.dumps(all_json_results, indent=2, ensure_ascii=False)
    elif args.output_format == "html":
        body = "\n\n".join(all_text_results)
        output = f'<!DOCTYPE html>\n<html>\n<head><meta charset="UTF-8"></head>\n<body>\n{body}\n</body>\n</html>'
    else:
        output = "\n\n".join(all_text_results)

    # Write output
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Résultat écrit dans {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
