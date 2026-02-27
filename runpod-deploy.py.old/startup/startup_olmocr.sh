#!/bin/bash
# ============================================================
# STARTUP SCRIPT — OLMoCR-7B
# Ce script est exécuté au démarrage du pod RunPod
# Il est stocké sur le Network Volume pour persister
# ============================================================
set -e

MODEL_ID="allenai/olmocr-7b-0225-preview"
MODEL_DIR="/workspace/models/olmocr-7b"
LOG_DIR="/workspace/logs"
HF_CACHE="/workspace/hf_cache"

mkdir -p "$LOG_DIR" "$HF_CACHE" "$(dirname $MODEL_DIR)"
export HF_HOME="$HF_CACHE"

echo "[$(date)] =========================================="
echo "[$(date)] Démarrage pod OLMoCR-7B"
echo "[$(date)] =========================================="

# ── 1. Dépendances ──────────────────────────────────────────
echo "[$(date)] Installation des dépendances..."
pip install --upgrade pip -q
pip install vllm open-webui huggingface_hub olmocr -q
echo "[$(date)] Dépendances installées."

# ── 2. Téléchargement du modèle ─────────────────────────────
if [ ! -d "$MODEL_DIR/model" ] && [ ! -f "$MODEL_DIR/config.json" ]; then
    echo "[$(date)] Téléchargement du modèle $MODEL_ID..."
    huggingface-cli download "$MODEL_ID" \
        --local-dir "$MODEL_DIR" \
        --token "$HF_TOKEN"
    echo "[$(date)] Modèle téléchargé dans $MODEL_DIR"
else
    echo "[$(date)] Modèle déjà présent dans $MODEL_DIR, skip."
fi

# ── 3. Lancement vLLM ───────────────────────────────────────
echo "[$(date)] Démarrage vLLM sur port 8000..."
vllm serve "$MODEL_DIR" \
    --served-model-name "olmocr" \
    --host 0.0.0.0 \
    --port 8000 \
    --dtype bfloat16 \
    --gpu-memory-utilization 0.88 \
    --max-model-len 8192 \
    --limit-mm-per-prompt image=1 \
    --trust-remote-code \
    > "$LOG_DIR/vllm_olmocr.log" 2>&1 &

VLLM_PID=$!
echo "[$(date)] vLLM démarré (PID: $VLLM_PID)"

# Attendre que l'API soit prête
echo "[$(date)] Attente de la disponibilité de l'API vLLM..."
until curl -s http://localhost:8000/v1/models > /dev/null 2>&1; do
    sleep 5
    echo "[$(date)]   ... en attente (voir $LOG_DIR/vllm_olmocr.log)"
done
echo "[$(date)] API vLLM disponible ✓"

# ── 4. Lancement Open WebUI ─────────────────────────────────
echo "[$(date)] Démarrage Open WebUI sur port 3000..."
DATA_DIR=/workspace/open-webui \
OPENAI_API_BASE_URLS="http://localhost:8000/v1" \
OPENAI_API_KEYS="dummy" \
WEBUI_AUTH=False \
open-webui serve \
    --host 0.0.0.0 \
    --port 3000 \
    > "$LOG_DIR/webui.log" 2>&1 &

echo "[$(date)] Open WebUI démarré ✓"
echo "[$(date)] =========================================="
echo "[$(date)] Pod OLMoCR-7B PRÊT"
echo "[$(date)]   vLLM API  : http://0.0.0.0:8000/v1"
echo "[$(date)]   Open WebUI: http://0.0.0.0:3000"
echo "[$(date)] =========================================="

# Maintenir le conteneur vivant
tail -f "$LOG_DIR/vllm_olmocr.log"
