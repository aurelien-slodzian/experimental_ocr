# CLAUDE.md — runpod-deploy

Contexte de déploiement GPU cloud pour le projet **Fuzzion** (système IA hybride combinant LLM et moteur d'inférence symbolique Loggic).

## Objectif

Déployer des pods RunPod en EU-RO-1 pour faire tourner deux modèles de vision :
- **OLMoCR-7B** — OCR de documents PDF (basé sur Qwen2-VL-7B)
- **Qwen3-VL-8B** — vision générale

Chaque pod expose :
- `port 8000` — vLLM (API OpenAI-compatible)
- `port 3000` — Open WebUI

## Infrastructure

- **Cloud** : RunPod Secure Cloud
- **Datacenter** : EU-RO-1 (Roumanie) — imposé par l'emplacement du Network Volume
- **GPU par ordre de préférence** : `NVIDIA L40S` → `NVIDIA A100 80GB PCIe` → `NVIDIA GeForce RTX 4090`
- **Network Volume** : monté sur `/workspace`, modèles cachés dans `/workspace/hf_cache`

## Décisions techniques

### API RunPod
- Utilisation de l'API **REST** (`rest.runpod.io/v1`) et non GraphQL ni SDK Python
- Raison : le SDK Python construit les requêtes GraphQL par concaténation de strings, le caractère `$` dans `dockerArgs` cassait les requêtes
- Champs importants du schéma REST actuel :
  - `dataCenterIds` (tableau, pas `dataCenterId`)
  - `dockerStartCmd` (tableau, pas `dockerArgs` string)
  - `startSsh` n'existe pas dans le REST API

### Startup scripts
- Le script de démarrage est encodé en base64 et passé via variable d'environnement `STARTUP_B64`
- Décodé au runtime par Python : `base64.b64decode(os.environ['STARTUP_B64'])`
- Evite tout problème d'échappement de caractères spéciaux dans le JSON

### Compatibilité macOS
- `base64 -i <fichier>` (pas `-w0` qui est GNU/Linux uniquement)
- `| tr -d '\n'` pour supprimer les sauts de ligne insérés tous les 76 caractères

## Structure des fichiers

```
runpod-deploy/
├── .env                    # RUNPOD_API_KEY, HF_TOKEN, PREFERRED_DATACENTER
├── .env.example
├── deploy_olmocr.sh        # Crée le pod OLMoCR
├── deploy_qwen3vl.sh       # Crée le pod Qwen3-VL
├── stop_pod.sh             # Arrête/supprime un pod
├── list_pods.sh            # Liste les pods actifs
├── CLAUDE.md               # Ce fichier
└── startup/
    ├── startup_olmocr.sh   # Installe vLLM, télécharge le modèle, démarre les serveurs
    └── startup_qwen3vl.sh
```

## Utilisation

```bash
cp .env.example .env   # Remplir RUNPOD_API_KEY et HF_TOKEN
chmod +x *.sh
./deploy_olmocr.sh     # Retourne le Pod ID et les URLs
```

URLs générées :
- `https://<pod_id>-8000.proxy.runpod.net/v1` — vLLM API
- `https://<pod_id>-3000.proxy.runpod.net`    — Open WebUI

Premier démarrage ~10 min (téléchargement modèle HuggingFace), redémarrages suivants ~30 sec (cache sur volume).

## Diagnostics GPU disponibles

L'API REST ne liste pas les GPU disponibles. Utiliser GraphQL :

```bash
curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ gpuTypes { id displayName memoryInGb securePrice lowestPrice { stockStatus } } }"}' \
  | python3 -m json.tool
```
