#!/usr/bin/env python3
"""
====================================================
LIST — Pods RunPod actifs
====================================================
Usage :
    python list_pods.py
====================================================
"""

import os
import sys
import runpod
from dotenv import load_dotenv

load_dotenv()

RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")

if not RUNPOD_API_KEY:
    print("❌ RUNPOD_API_KEY manquant dans .env")
    sys.exit(1)

runpod.api_key = RUNPOD_API_KEY

try:
    pods = runpod.get_pods()

    if not pods:
        print("Aucun pod actif.")
        sys.exit(0)

    print(f"\n{'ID':<20} {'Nom':<25} {'Status':<12} {'GPU':<15} {'URLs'}")
    print("─" * 100)

    for pod in pods:
        pod_id   = pod.get("id", "N/A")
        name     = pod.get("name", "N/A")
        status   = pod.get("desiredStatus", "N/A")
        gpu      = pod.get("machine", {}).get("gpuDisplayName", "N/A")
        api_url  = f"https://{pod_id}-8000.proxy.runpod.net/v1"
        webui_url = f"https://{pod_id}-3000.proxy.runpod.net"

        print(f"{pod_id:<20} {name:<25} {status:<12} {gpu:<15}")
        print(f"{'':20} {'':25} API    : {api_url}")
        print(f"{'':20} {'':25} WebUI  : {webui_url}")
        print()

except Exception as e:
    print(f"❌ Erreur : {e}")
    sys.exit(1)
