#!/usr/bin/env bash
# ============================================================
# DEPLOY — Pod OLMoCR-7B sur RunPod L40S
# Compatible macOS (zsh/bash) et Linux
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Fichier .env introuvable. Copie .env.example en .env et remplis les valeurs."
    exit 1
fi

source "$ENV_FILE"

: "${RUNPOD_API_KEY:?RUNPOD_API_KEY manquant dans .env}"
: "${HF_TOKEN:?HF_TOKEN manquant dans .env}"
DATACENTER="${PREFERRED_DATACENTER:-EU-RO-1}"

# Compatible macOS : base64 -i <fichier>, supprime les retours à la ligne avec tr
STARTUP_B64=$(base64 -i "$SCRIPT_DIR/startup/startup_olmocr.sh" | tr -d '\n')

PAYLOAD=$(cat <<JSON
{
  "name": "fuzzion-olmocr",
  "imageName": "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04",
  "gpuTypeIds": ["NVIDIA L40S", "NVIDIA A100 80GB PCIe", "NVIDIA GeForce RTX 4090"],
  "cloudType": "SECURE",
  "dataCenterIds": ["${DATACENTER}"],
  "gpuCount": 1,
  "containerDiskInGb": 50,
  "volumeInGb": 60,
  "volumeMountPath": "/workspace",
  "ports": ["22/tcp", "8000/http", "3000/http"],
  "env": {
    "HF_TOKEN": "${HF_TOKEN}",
    "HF_HOME": "/workspace/hf_cache",
    "PYTHONUNBUFFERED": "1",
    "STARTUP_B64": "${STARTUP_B64}"
  },
  "dockerStartCmd": ["/bin/bash", "-c", "python3 -c \"import os,base64; open('/startup.sh','w').write(base64.b64decode(os.environ['STARTUP_B64']).decode())\" && chmod +x /startup.sh && bash /startup.sh"]
}
JSON
)

echo "Création du pod fuzzion-olmocr (L40S Secure Cloud, ${DATACENTER})..."

RESPONSE=$(curl -s -X POST "https://rest.runpod.io/v1/pods" \
    -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

POD_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null || true)

if [[ -z "$POD_ID" ]]; then
    echo "Erreur lors de la création du pod :"
    echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
    exit 1
fi

echo ""
echo "Pod créé avec succès !"
echo "   Pod ID     : $POD_ID"
echo ""
echo "URLs (disponibles dans ~5 min) :"
echo "   vLLM API   : https://${POD_ID}-8000.proxy.runpod.net/v1"
echo "   Open WebUI : https://${POD_ID}-3000.proxy.runpod.net"
echo "   SSH        : RunPod dashboard -> Connect -> SSH"
echo ""
echo "Logs (via SSH) :"
echo "   tail -f /workspace/logs/vllm_olmocr.log"
echo "   tail -f /workspace/logs/webui.log"
echo ""
echo "Pour arrêter : ./stop_pod.sh $POD_ID"
