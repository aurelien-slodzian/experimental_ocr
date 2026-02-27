#!/usr/bin/env python3
"""
====================================================
STOP/TERMINATE — Pod RunPod
====================================================
Usage :
    python stop_pod.py <pod_id>          # arrête le pod (conserve le volume)
    python stop_pod.py <pod_id> --delete # supprime définitivement le pod
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

if len(sys.argv) < 2:
    print("Usage : python stop_pod.py <pod_id> [--delete]")
    sys.exit(1)

pod_id = sys.argv[1]
delete = "--delete" in sys.argv

runpod.api_key = RUNPOD_API_KEY

try:
    if delete:
        print(f"🗑️  Suppression définitive du pod {pod_id}...")
        runpod.terminate_pod(pod_id)
        print("✅ Pod supprimé. Le volume réseau est conservé.")
    else:
        print(f"⏹️  Arrêt du pod {pod_id} (volume conservé)...")
        runpod.stop_pod(pod_id)
        print("✅ Pod arrêté. Facture stoppée.")
        print("   Pour le relancer : dashboard RunPod → pod → Resume")
        print("   Pour supprimer   : python stop_pod.py <pod_id> --delete")

except Exception as e:
    print(f"❌ Erreur : {e}")
    sys.exit(1)
