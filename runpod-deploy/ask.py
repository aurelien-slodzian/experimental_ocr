#!/usr/bin/env python3
"""Interrogation ciblée d'une image via vLLM sur RunPod.

Envoie une image avec une ou plusieurs questions et retourne les réponses.

Deux modes :
  - batch       : toutes les questions en une seule requête (défaut)
  - interactif  : conversation multi-tour avec cache serveur (--interactive)
                  Nécessite --enable-prefix-caching dans le startup vLLM.

Usage :
  python ask.py photo.jpg "Quel texte apparaît au-dessus du mot Nom ?"
  python ask.py photo.jpg "Q1 ?" "Q2 ?" "Q3 ?"
  python ask.py photo.jpg --model chandra --questions-file questions.txt
  python ask.py photo.jpg --interactive
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


# ── Backends ─────────────────────────────────────────────────

BACKENDS: dict[str, dict[str, str]] = {
    "qwen3":   {"env_var": "QWEN3VL_POD_ID",  "model_name": "qwen3-vl"},
    "chandra": {"env_var": "CHANDRA_POD_ID",   "model_name": "chandra"},
}


# ── Image helper ─────────────────────────────────────────────

def image_to_base64(image_path: str) -> tuple[str, str]:
    path = Path(image_path)
    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",  ".webp": "image/webp",
        ".bmp": "image/bmp",  ".tiff": "image/tiff", ".tif": "image/tiff",
    }
    mime = mime_map.get(path.suffix.lower(), "image/jpeg")
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return data, mime


def image_content_block(img_b64: str, mime: str) -> dict:
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{img_b64}"},
    }


# ── Batch mode ───────────────────────────────────────────────

BATCH_SYSTEM = (
    "You are a precise document analysis assistant. "
    "Answer each question using only information visible in the provided image. "
    "Be concise and exact — return only the extracted value, no explanation."
)

def build_batch_prompt(questions: list[str]) -> str:
    lines = [
        "Answer the following questions about the image.",
        "Return a JSON object with question numbers as keys (\"1\", \"2\", …) "
        "and the extracted answers as string values.",
        "If the answer is not visible, use null.",
        "Return ONLY the JSON object, no markdown fences.",
        "",
    ]
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q}")
    return "\n".join(lines)


def ask_batch(client: OpenAI, model: str, img_b64: str, mime: str,
              questions: list[str]) -> dict[str, str | None]:
    prompt = build_batch_prompt(questions)
    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": BATCH_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    image_content_block(img_b64, mime),
                ],
            },
        ],
        temperature=0.0,
        max_tokens=1024,
        extra_body={"repetition_penalty": 1.15},
        stream=True,
    )
    parts: list[str] = []
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            parts.append(chunk.choices[0].delta.content)
    raw = "".join(parts).strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": raw}


# ── Interactive mode ─────────────────────────────────────────

def run_interactive(client: OpenAI, model: str, img_b64: str, mime: str,
                    image_path: str) -> None:
    """Multi-turn conversation. The image is sent once in the first message;
    subsequent turns reuse the server-side KV cache (requires
    --enable-prefix-caching in vLLM)."""
    print(f"Image : {image_path}")
    print("Mode interactif — posez vos questions (Ctrl+D ou 'quit' pour quitter)\n")

    messages: list[dict] = [
        {"role": "system", "content": BATCH_SYSTEM},
    ]
    first_turn = True

    while True:
        try:
            question = input("Question : ").strip()
        except EOFError:
            break
        if not question or question.lower() in ("quit", "exit", "q"):
            break

        if first_turn:
            # Include the image only on the first turn
            content = [
                {"type": "text", "text": question},
                image_content_block(img_b64, mime),
            ]
            first_turn = False
        else:
            content = question  # type: ignore[assignment]

        messages.append({"role": "user", "content": content})

        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=512,
            extra_body={"repetition_penalty": 1.15},
            stream=True,
        )
        parts: list[str] = []
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
        answer = "".join(parts)
        messages.append({"role": "assistant", "content": answer})
        print(f"Réponse : {answer}\n")


# ── Main ─────────────────────────────────────────────────────

def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Interrogation ciblée d'une image via vLLM sur RunPod"
    )
    parser.add_argument("image", help="Chemin vers l'image (JPEG, PNG…)")
    parser.add_argument(
        "questions", nargs="*",
        help="Questions à poser (une ou plusieurs, entre guillemets)",
    )
    parser.add_argument(
        "--model", choices=list(BACKENDS), default="qwen3",
        help="Modèle à utiliser : qwen3 (défaut) ou chandra",
    )
    parser.add_argument(
        "--questions-file", "-f", default=None,
        help="Fichier texte contenant une question par ligne",
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true",
        help="Mode interactif multi-tour (nécessite --enable-prefix-caching sur vLLM)",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Fichier de sortie JSON (batch uniquement, défaut : stdout)",
    )
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"Erreur : fichier introuvable : {image_path}", file=sys.stderr)
        sys.exit(1)

    backend = BACKENDS[args.model]
    pod_id = os.environ.get(backend["env_var"])
    if not pod_id:
        print(f"Erreur : {backend['env_var']} manquant dans .env", file=sys.stderr)
        sys.exit(1)

    model_name = backend["model_name"]
    client = OpenAI(
        base_url=f"https://{pod_id}-8000.proxy.runpod.net/v1",
        api_key="not-needed",
    )
    print(f"Backend : {args.model} ({model_name})", file=sys.stderr)

    print(f"Chargement de l'image {image_path.name}…", file=sys.stderr)
    img_b64, mime = image_to_base64(str(image_path))

    if args.interactive:
        run_interactive(client, model_name, img_b64, mime, str(image_path))
        return

    # Collect questions
    questions = list(args.questions)
    if args.questions_file:
        qs_path = Path(args.questions_file)
        if not qs_path.exists():
            print(f"Erreur : fichier introuvable : {qs_path}", file=sys.stderr)
            sys.exit(1)
        for line in qs_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                questions.append(line)

    if not questions:
        print("Erreur : aucune question fournie. "
              "Utilisez des arguments positionnels, --questions-file, ou --interactive.",
              file=sys.stderr)
        sys.exit(1)

    print(f"Envoi de {len(questions)} question(s)…", file=sys.stderr)
    results = ask_batch(client, model_name, img_b64, mime, questions)

    # Format output: align questions with answers
    output_data = {
        str(i): {"question": q, "answer": results.get(str(i))}
        for i, q in enumerate(questions, 1)
    }
    output = json.dumps(output_data, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Résultat écrit dans {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
