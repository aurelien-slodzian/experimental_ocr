#!/usr/bin/env bash
# ============================================================
# LIST — Pods RunPod actifs via REST API
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.env"

: "${RUNPOD_API_KEY:?RUNPOD_API_KEY manquant dans .env}"

RESPONSE=$(curl -s "https://rest.runpod.io/v1/pods" \
    -H "Authorization: Bearer ${RUNPOD_API_KEY}")

echo "$RESPONSE" | python3 -c "
import sys, json
pods = json.load(sys.stdin)
if not pods:
    print('Aucun pod actif.')
    sys.exit(0)
print()
for p in pods:
    pid = p.get('id','?')
    name = p.get('name','?')
    status = p.get('desiredStatus','?')
    gpu = p.get('machine',{}).get('gpuDisplayName','?')
    print(f'  ID     : {pid}')
    print(f'  Nom    : {name}')
    print(f'  Status : {status}')
    print(f'  GPU    : {gpu}')
    print(f'  API    : https://{pid}-8000.proxy.runpod.net/v1')
    print(f'  WebUI  : https://{pid}-3000.proxy.runpod.net')
    print()
"
