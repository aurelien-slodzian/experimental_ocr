# RunPod Deploy — Qwen3-VL-8B & OLMoCR

Déploiement en quelques commandes de deux pods RunPod indépendants,
chacun avec un L40S 48 GB, vLLM (API OpenAI-compatible) et Open WebUI.

```
runpod-deploy/
├── .env.example              ← copier en .env et remplir
├── scripts/
│   ├── deploy_qwen3vl.py     ← déploie le pod Qwen3-VL-8B
│   ├── deploy_olmocr.py      ← déploie le pod OLMoCR-7B
│   ├── stop_pod.py           ← arrête ou supprime un pod
│   └── list_pods.py          ← liste les pods actifs
└── startup/
    ├── startup_qwen3vl.sh    ← script de démarrage Qwen3-VL (auto-exécuté)
    └── startup_olmocr.sh     ← script de démarrage OLMoCR   (auto-exécuté)
```

---

## Prérequis (une seule fois)

```bash
pip install runpod python-dotenv
```

---

## 1. Configuration

```bash
cp .env.example .env
# Éditer .env avec ta clé RunPod et ton token HuggingFace
```

**Où trouver les clés :**
- `RUNPOD_API_KEY` → RunPod Dashboard → Settings → API Keys
- `HF_TOKEN` → https://huggingface.co/settings/tokens

---

## 2. Déployer un pod

```bash
cd scripts/

# Pod Qwen3-VL-8B (port 8000 vLLM + port 3000 WebUI)
python deploy_qwen3vl.py

# Pod OLMoCR-7B (port 8000 vLLM + port 3000 WebUI)
python deploy_olmocr.py
```

Le script affiche :
- Le Pod ID
- L'URL de l'API vLLM
- L'URL Open WebUI

**Délai de disponibilité :** ~5 min (téléchargement du modèle au 1er démarrage,
~30 sec les fois suivantes si le Network Volume est conservé).

---

## 3. Accéder aux services

| Service    | URL                                          |
|------------|----------------------------------------------|
| vLLM API   | `https://<pod_id>-8000.proxy.runpod.net/v1`  |
| Open WebUI | `https://<pod_id>-3000.proxy.runpod.net`     |
| SSH        | RunPod Dashboard → pod → Connect → SSH       |

---

## 4. Arrêter un pod (stoppe la facturation)

```bash
# Arrêt simple (volume conservé, pod relançable depuis le dashboard)
python stop_pod.py <pod_id>

# Suppression définitive
python stop_pod.py <pod_id> --delete
```

---

## 5. Lister les pods actifs

```bash
python list_pods.py
```

---

## Notes

- Les modèles (~15 GB chacun) sont téléchargés dans `/workspace/models/`
  sur le Network Volume lors du **premier démarrage uniquement**.
  En cas d'arrêt/relance, les modèles sont déjà présents → démarrage rapide.

- `WEBUI_AUTH=False` dans les startup scripts désactive l'authentification
  Open WebUI. Si le pod est exposé publiquement, mettre `WEBUI_AUTH=True`
  et définir `WEBUI_SECRET_KEY`.

- Pour un datacenter européen : `PREFERRED_DATACENTER=EU-RO-1` (Roumanie)
  ou `EUR-IS-1` (Islande). Laisser vide pour le choix automatique RunPod.
