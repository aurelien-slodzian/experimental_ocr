#!/usr/bin/env bash
# ============================================================
# DEPLOY — Pod Qwen3-VL-8B sur RunPod
# Compatible macOS (zsh/bash) et Linux
#
# Usage : ./deploy_qwen3vl.sh [--gpu l40s|a100|4090]
#   --gpu l40s   → NVIDIA L40S uniquement
#   --gpu a100   → NVIDIA A100 80GB PCIe uniquement
#   --gpu 4090   → NVIDIA GeForce RTX 4090 uniquement
#   (défaut)     → les 3 GPU autorisés, par ordre de préférence
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
: "${NETWORK_VOLUME_ID:?NETWORK_VOLUME_ID manquant dans .env}"
DATACENTER="${PREFERRED_DATACENTER:-EU-RO-1}"

# ── GPU selection ────────────────────────────────────────────
GPU_IDS='["NVIDIA L40S", "NVIDIA A100 80GB PCIe", "NVIDIA GeForce RTX 4090"]'
GPU_LABEL="L40S / A100 / 4090"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --gpu)
            shift
            case "$(echo "$1" | tr '[:upper:]' '[:lower:]')" in
                l40s)  GPU_IDS='["NVIDIA L40S"]';               GPU_LABEL="L40S" ;;
                a100)  GPU_IDS='["NVIDIA A100 80GB PCIe"]';     GPU_LABEL="A100 80GB" ;;
                4090)  GPU_IDS='["NVIDIA GeForce RTX 4090"]';   GPU_LABEL="RTX 4090" ;;
                *)
                    echo "GPU inconnu : $1. Valeurs acceptées : l40s, a100, 4090"
                    exit 1
                    ;;
            esac
            shift
            ;;
        *)
            echo "Option inconnue : $1"
            echo "Usage : $0 [--gpu l40s|a100|4090]"
            exit 1
            ;;
    esac
done

# Compatible macOS : base64 sans -w0, on supprime les retours à la ligne avec tr
STARTUP_B64=$(base64 -i "$SCRIPT_DIR/startup/startup_qwen3vl.sh" | tr -d '\n')

PAYLOAD=$(cat <<JSON
{
  "name": "fuzzion-qwen3vl",
  "imageName": "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04",
  "gpuTypeIds": ${GPU_IDS},
  "cloudType": "SECURE",
  "dataCenterIds": ["${DATACENTER}"],
  "gpuCount": 1,
  "containerDiskInGb": 50,
  "networkVolumeId": "${NETWORK_VOLUME_ID}",
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

echo "Création du pod fuzzion-qwen3vl (${GPU_LABEL}, Secure Cloud, ${DATACENTER})..."

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
echo "   tail -f /workspace/logs/vllm_qwen3vl.log"
echo "   tail -f /workspace/logs/webui.log"
echo ""
echo "Pour arrêter : ./stop_pod.sh $POD_ID"
