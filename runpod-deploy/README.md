# RunPod Deploy — Qwen3-VL-8B & OLMoCR

Scripts shell purs (curl + REST API RunPod). Aucune dépendance Python.

```
runpod-deploy/
├── .env.example          ← copier en .env et remplir
├── deploy_qwen3vl.sh     ← déploie le pod Qwen3-VL-8B   (./deploy_qwen3vl.sh)
├── deploy_olmocr.sh      ← déploie le pod OLMoCR-7B     (./deploy_olmocr.sh)
├── stop_pod.sh           ← arrête ou supprime un pod     (./stop_pod.sh <id>)
├── list_pods.sh          ← liste les pods actifs         (./list_pods.sh)
└── startup/
    ├── startup_qwen3vl.sh   ← exécuté au démarrage du pod Qwen3-VL
    └── startup_olmocr.sh    ← exécuté au démarrage du pod OLMoCR
```

## Prérequis

- `curl` (présent sur macOS/Linux par défaut)
- `python3` (pour décoder la réponse JSON — présent par défaut)
- Pas de pip, pas de venv, pas de SDK

## 1. Configuration

```bash
cp .env.example .env
# Éditer .env avec ta clé RunPod et ton token HuggingFace
```

- `RUNPOD_API_KEY` → RunPod Dashboard → Settings → API Keys
- `HF_TOKEN`       → https://huggingface.co/settings/tokens

## 2. Déployer

```bash
chmod +x *.sh
./deploy_olmocr.sh    # pod OLMoCR
./deploy_qwen3vl.sh   # pod Qwen3-VL
```

## 3. URLs

| Service    | URL                                         |
|------------|---------------------------------------------|
| vLLM API   | https://<pod_id>-8000.proxy.runpod.net/v1   |
| Open WebUI | https://<pod_id>-3000.proxy.runpod.net      |
| SSH        | RunPod Dashboard → pod → Connect → SSH      |

## 4. Arrêter / Supprimer

```bash
./stop_pod.sh <pod_id>           # arrête (volume conservé)
./stop_pod.sh <pod_id> --delete  # supprime définitivement
```

## 5. Lister les pods

```bash
./list_pods.sh
```

## Notes

- Les modèles (~15 GB) sont téléchargés dans `/workspace/models/`
  au **premier démarrage uniquement**. Les relances suivantes sont rapides.
- `WEBUI_AUTH=False` : authentification Open WebUI désactivée.
  Mettre `True` si le pod est exposé publiquement.
- Datacenter par défaut : `EU-RO-1` (Roumanie). Changer dans `.env`.
