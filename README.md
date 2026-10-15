# Anima-IA-Animesito

Local anime image studio: a JFast backend and a React frontend inside WSL,
driving ComfyUI (images) and Ollama ("Mejorar con IA") that run natively on
Windows.

## Requirements

- Windows 11 with a WSL 2 distro (Ubuntu) where this repo is cloned, and
  `networkingMode=mirrored` under `[wsl2]` in `%USERPROFILE%\.wslconfig`.
- Inside WSL: Docker Engine with the compose plugin, and Node 20+ for Linux.
  `uv` is installed by the installer if missing.
- On Windows: ComfyUI (default `Desktop\ComfyUI`) with its models, and
  optionally Ollama.

## Install

From Windows, open the repo folder (`\\wsl.localhost\<distro>\...`) and run
`Instalar.bat`. If ComfyUI lives elsewhere: `Instalar.bat -ComfyDir "D:\ComfyUI"`.

It creates `.env` and `animesito/.env` (random database password), the Python
venv, the frontend packages, starts PostgreSQL and Redis, runs the migrations,
checks the content policy and lists which local models the app will offer.
Running it again keeps the existing `.env` files.

From WSL directly: `bash scripts/install.sh --comfy-models /mnt/c/.../ComfyUI/models`.

## Start

`Iniciar.bat` starts ComfyUI and Ollama if they are down, then the app in its
own window, and opens http://127.0.0.1:7799 (not `localhost`: Windows tries
`::1` first, which mirrored WSL does not forward). Closing that window stops
the app.

From WSL directly: `bash scripts/dev.sh`.

## Models

Nothing is copied: the app asks ComfyUI for its checkpoints (`models/checkpoints`)
and Flux GGUF files (`models/diffusion_models`), and reads each file's header
from `JFAST_COMFY_MODELS_DIR` to detect the family and v-prediction. Video,
inpaint, Kontext and unknown architectures are left out of the selector. To see
the list without starting anything:

```bash
cd animesito && PYTHONPATH=. .venv/bin/python ../scripts/models_report.py \
  "$(sed -n 's/^JFAST_COMFY_MODELS_DIR=//p' .env)"
```
