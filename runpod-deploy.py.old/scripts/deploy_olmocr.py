#!/usr/bin/env python3
"""
====================================================
DEPLOY — Pod OLMoCR-7B sur RunPod L40S
====================================================
Usage :
    pip install runpod python-dotenv
    python deploy_olmocr.py

Ce script crée un pod RunPod Secure Cloud avec :
  - GPU   : 1× NVIDIA L40S (48 GB)
  - Image : runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04
  - Ports : 22 (SSH), 8000 (vLLM API), 3000 (Open WebUI)
  - Startup : startup/startup_olmocr.sh (copié sur le Network Volume)
====================================================
"""

import os
import sys
import base64
import runpod
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ────────────────────────────────────────────
RUNPOD_API_KEY    = os.getenv("RUNPOD_API_KEY")
HF_TOKEN          = os.getenv("HF_TOKEN")
NETWORK_VOLUME_ID = os.getenv("NETWORK_VOLUME_ID_OLMOCR", "")  # optionnel
DATACENTER        = os.getenv("PREFERRED_DATACENTER", "EU-RO-1")

POD_NAME          = "fuzzion-olmocr"
GPU_TYPE          = "NVIDIA L40S"
IMAGE             = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"
CONTAINER_DISK    = 50     # GB
VOLUME_SIZE       = 60     # GB (modèle OLMoCR ~15 GB + marge)
VOLUME_MOUNT      = "/workspace"

# Lecture et encodage du script de démarrage
with open("startup/startup_olmocr.sh", "r") as f:
    STARTUP_SCRIPT = f.read()

STARTUP_B64 = base64.b64encode(STARTUP_SCRIPT.encode()).decode()

# Le script est passé via variable d'env (évite les pb GraphQL avec docker_args)
DOCKER_ARGS = 'bash -c "echo $STARTUP_B64 | base64 -d > /startup.sh && chmod +x /startup.sh && bash /startup.sh"'

# ── Validation ───────────────────────────────────────────────
if not RUNPOD_API_KEY:
    print("❌ RUNPOD_API_KEY manquant dans .env")
    sys.exit(1)

if not HF_TOKEN:
    print("❌ HF_TOKEN manquant dans .env")
    sys.exit(1)

# ── Déploiement ──────────────────────────────────────────────
runpod.api_key = RUNPOD_API_KEY

print(f"🚀 Création du pod '{POD_NAME}'...")
print(f"   GPU         : {GPU_TYPE}")
print(f"   Datacenter  : {DATACENTER}")
print(f"   Image       : {IMAGE}")
print(f"   Modèle      : OLMoCR-7B-0225-preview")

pod_config = dict(
    name=POD_NAME,
    image_name=IMAGE,
    gpu_type_id=GPU_TYPE,
    cloud_type="SECURE",
    data_center_id=DATACENTER if DATACENTER else None,
    gpu_count=1,
    container_disk_in_gb=CONTAINER_DISK,
    ports="22/tcp,8000/http,3000/http",
    env={
        "HF_TOKEN": HF_TOKEN,
        "HF_HOME": "/workspace/hf_cache",
        "PYTHONUNBUFFERED": "1",
        "STARTUP_B64": STARTUP_B64,
    },
    docker_args=DOCKER_ARGS,
    start_ssh=True,
)

if NETWORK_VOLUME_ID:
    pod_config["network_volume_id"] = NETWORK_VOLUME_ID
    print(f"   Volume      : Network Volume existant ({NETWORK_VOLUME_ID})")
else:
    pod_config["volume_in_gb"] = VOLUME_SIZE
    pod_config["volume_mount_path"] = VOLUME_MOUNT
    print(f"   Volume      : Nouveau volume {VOLUME_SIZE} GB → {VOLUME_MOUNT}")

try:
    pod = runpod.create_pod(**pod_config)
    pod_id = pod.get("id", "N/A")

    print()
    print("✅ Pod créé avec succès !")
    print(f"   Pod ID      : {pod_id}")
    print(f"   Status      : {pod.get('desiredStatus', 'STARTING')}")
    print()
    print("🌐 URLs (disponibles dans 3-5 min après démarrage du modèle) :")
    print(f"   vLLM API    : https://{pod_id}-8000.proxy.runpod.net/v1")
    print(f"   Open WebUI  : https://{pod_id}-3000.proxy.runpod.net")
    print(f"   SSH         : Dans RunPod dashboard → Connect → SSH")
    print()
    print("📋 Logs :")
    print(f"   vLLM        : /workspace/logs/vllm_olmocr.log")
    print(f"   WebUI       : /workspace/logs/webui.log")
    print()
    print("⏹️  Pour arrêter le pod :")
    print(f"   python stop_pod.py {pod_id}")

except Exception as e:
    print(f"❌ Erreur lors de la création du pod : {e}")
    sys.exit(1)
