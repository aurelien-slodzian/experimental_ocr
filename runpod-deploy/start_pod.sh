#!/usr/bin/env bash
# ============================================================
# START/RESUME — Pod RunPod via REST API
# ============================================================
# Usage :
#   ./start_pod.sh <pod_id>        # redémarre un pod arrêté
#   ./start_pod.sh                 # liste les pods arrêtés et propose d'en relancer un
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.env"

: "${RUNPOD_API_KEY:?RUNPOD_API_KEY manquant dans .env}"

start_pod() {
    local pod_id="$1"
    echo "Démarrage du pod $pod_id..."
    RESPONSE=$(curl -s -X POST "https://rest.runpod.io/v1/pods/${pod_id}/start" \
        -H "Authorization: Bearer ${RUNPOD_API_KEY}")

    # Check for errors in response
    ERROR=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('error',''))
except: pass
" 2>/dev/null || true)

    if [[ -n "$ERROR" ]]; then
        echo "Erreur : $ERROR"
        echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || true
        exit 1
    fi

    echo "Pod $pod_id démarré."
    echo ""
    echo "URLs (disponibles dans quelques instants) :"
    echo "   vLLM API   : https://${pod_id}-8000.proxy.runpod.net/v1"
    echo "   Open WebUI : https://${pod_id}-3000.proxy.runpod.net"
    echo ""
    echo "Pour arrêter : ./stop_pod.sh $pod_id"
}

if [[ $# -ge 1 ]]; then
    start_pod "$1"
    exit 0
fi

# No pod_id given — list stopped pods and let user pick
RESPONSE=$(curl -s "https://rest.runpod.io/v1/pods" \
    -H "Authorization: Bearer ${RUNPOD_API_KEY}")

STOPPED=$(echo "$RESPONSE" | python3 -c "
import sys, json
pods = json.load(sys.stdin)
stopped = [p for p in pods if p.get('desiredStatus') in ('EXITED', 'STOPPED')]
if not stopped:
    print('NONE')
    sys.exit(0)
for i, p in enumerate(stopped, 1):
    pid = p.get('id','?')
    name = p.get('name','?')
    gpu = p.get('machine',{}).get('gpuDisplayName','?')
    print(f'{i}) {pid}  {name}  [{gpu}]')
" 2>/dev/null)

if [[ "$STOPPED" == "NONE" ]]; then
    echo "Aucun pod arrêté à redémarrer."
    echo "Pods actifs :"
    "$SCRIPT_DIR/list_pods.sh"
    exit 0
fi

echo "Pods arrêtés :"
echo ""
echo "$STOPPED"
echo ""
read -rp "Numéro du pod à démarrer (ou Entrée pour annuler) : " CHOICE

if [[ -z "$CHOICE" ]]; then
    echo "Annulé."
    exit 0
fi

POD_ID=$(echo "$RESPONSE" | python3 -c "
import sys, json
pods = json.load(sys.stdin)
stopped = [p for p in pods if p.get('desiredStatus') in ('EXITED', 'STOPPED')]
idx = int(sys.argv[1]) - 1
if 0 <= idx < len(stopped):
    print(stopped[idx]['id'])
" "$CHOICE" 2>/dev/null)

if [[ -z "$POD_ID" ]]; then
    echo "Choix invalide."
    exit 1
fi

start_pod "$POD_ID"
