#!/usr/bin/env python3
"""OCR d'un fichier PDF via OLMoCR déployé sur RunPod."""

import argparse
import os
import sys
from pathlib import Path

import pypdfium2 as pdfium
from dotenv import load_dotenv
from openai import OpenAI
from olmocr.data.renderpdf import render_pdf_to_base64png
from olmocr.prompts import build_no_anchoring_v4_yaml_prompt


def get_page_count(pdf_path: str) -> int:
    doc = pdfium.PdfDocument(pdf_path)
    count = len(doc)
    doc.close()
    return count


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


def ocr_page(client: OpenAI, model: str, pdf_path: str, page_num: int) -> str:
    """Extrait le texte d'une page PDF via OLMoCR."""
    # page_num est 1-based, render_pdf_to_base64png attend 0-based
    img_base64 = render_pdf_to_base64png(pdf_path, page_num - 1, target_longest_image_dim=1288)
    prompt_text = build_no_anchoring_v4_yaml_prompt()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_base64}"},
                    },
                ],
            }
        ],
        temperature=0.0,
        max_tokens=4096,
    )
    return response.choices[0].message.content


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="OCR d'un PDF via OLMoCR sur RunPod")
    parser.add_argument("pdf", help="Chemin vers le fichier PDF")
    parser.add_argument("--pod-id", default=None, help="ID du pod RunPod (défaut : OLMOCR_POD_ID du .env)")
    parser.add_argument("--pages", default=None, help="Pages à traiter : 3, 1-5, 2,4,7-9 (défaut : toutes)")
    parser.add_argument("--output", "-o", default=None, help="Fichier de sortie (défaut : stdout)")
    parser.add_argument("--model", default="olmocr", help="Nom du modèle vLLM (défaut : olmocr)")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"Erreur : fichier introuvable : {pdf_path}", file=sys.stderr)
        sys.exit(1)

    pod_id = args.pod_id or os.environ.get("OLMOCR_POD_ID")
    if not pod_id:
        print("Erreur : --pod-id requis ou OLMOCR_POD_ID dans .env", file=sys.stderr)
        sys.exit(1)

    base_url = f"https://{pod_id}-8000.proxy.runpod.net/v1"
    client = OpenAI(base_url=base_url, api_key="not-needed")

    total_pages = get_page_count(str(pdf_path))
    if args.pages:
        pages = parse_page_range(args.pages, total_pages)
    else:
        pages = list(range(1, total_pages + 1))

    print(f"PDF : {pdf_path.name} — {total_pages} page(s), traitement de {len(pages)} page(s)", file=sys.stderr)

    results = []
    for page_num in pages:
        print(f"  Page {page_num}/{total_pages}...", file=sys.stderr, end=" ", flush=True)
        text = ocr_page(client, args.model, str(pdf_path), page_num)
        results.append(text)
        print("OK", file=sys.stderr)

    output_text = "\n\n".join(results)

    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"Résultat écrit dans {args.output}", file=sys.stderr)
    else:
        print(output_text)


if __name__ == "__main__":
    main()
