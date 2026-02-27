#!/usr/bin/env bash
# ============================================================
# STOP/TERMINATE — Pod RunPod via REST API
# ============================================================
# Usage :
#   ./stop_pod.sh <pod_id>           # arrête (facture stoppée, volume conservé)
#   ./stop_pod.sh <pod_id> --delete  # supprime définitivement
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.env"

: "${RUNPOD_API_KEY:?RUNPOD_API_KEY manquant dans .env}"

if [[ $# -lt 1 ]]; then
    echo "Usage : ./stop_pod.sh <pod_id> [--delete]"
    exit 1
fi

POD_ID="$1"
DELETE="${2:-}"

if [[ "$DELETE" == "--delete" ]]; then
    echo "Suppression définitive du pod $POD_ID..."
    RESPONSE=$(curl -s -X DELETE "https://rest.runpod.io/v1/pods/${POD_ID}" \
        -H "Authorization: Bearer ${RUNPOD_API_KEY}")
    echo "Pod supprimé. Volume réseau conservé."
else
    echo "Arrêt du pod $POD_ID (volume conservé, facture stoppée)..."
    RESPONSE=$(curl -s -X POST "https://rest.runpod.io/v1/pods/${POD_ID}/stop" \
        -H "Authorization: Bearer ${RUNPOD_API_KEY}")
    echo "Pod arrêté."
    echo "Pour relancer : ./start_pod.sh $POD_ID"
    echo "Pour supprimer : ./stop_pod.sh $POD_ID --delete"
fi

echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || true
