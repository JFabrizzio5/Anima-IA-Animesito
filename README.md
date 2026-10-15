# Anima-IA-Animesito

Local anime image studio: a JFast backend and a React frontend inside WSL,
driving ComfyUI (images) and Ollama ("Mejorar con IA") that run natively on
Windows.

## Requirements

- Windows 11 with a WSL 2 distro (Ubuntu) where this repo is cloned, and
  `networkingMode=mirrored` under `[wsl2]` in `%USERPROFILE%\.wslconfig`.
- Inside WSL: Docker Engine with the compose plugin, and Node 20+ for Linux.
  `uv` is installed by the installer if missing.
- On Windows: ComfyUI (default `Desktop\ComfyUI`; the installer adds the
  models), and optionally Ollama.

## Install

From Windows, open the repo folder (`\\wsl.localhost\<distro>\...`) and run
`Instalar.bat`. If ComfyUI lives elsewhere: `Instalar.bat -ComfyDir "D:\ComfyUI"`.

It creates `.env` and `animesito/.env` (random database password), the Python
venv, the frontend packages, starts PostgreSQL and Redis, runs the migrations,
checks the content policy, downloads the models and lists which ones the app
will offer. Running it again keeps the existing `.env` files and resumes any
interrupted download.

From WSL directly: `bash scripts/install.sh --comfy-models /mnt/c/.../ComfyUI/models`.

## Start

`Iniciar.bat` starts ComfyUI and Ollama if they are down, then the app in its
own window, and opens http://127.0.0.1:7799 (not `localhost`: Windows tries
`::1` first, which mirrored WSL does not forward). Closing that window stops
the app.

From WSL directly: `bash scripts/dev.sh`.

## Models

`scripts/models.toml` lists what the installer can download, in sets:

| Set | Size | What |
| --- | --- | --- |
| `base` (default) | ~10 GB | WAI Illustrious + `dolphin-mistral` for "Mejorar con IA" |
| `anime` | ~19.5 GB | NoobAI v-pred, Animagine XL 3.1, Pony Diffusion V6 |
| `realistic` | ~13 GB | RealVisXL V4.0, Juggernaut XL v9 |
| `flux` | ~13.4 GB | Flux dev Q5_K_S GGUF, text encoders, VAE, adult LoRA, ComfyUI-GGUF node |
| `extra` | ~16 GB | Flux dev Q8_0, `dolphin-llama3` |

The installer asks which sets to fetch; or pass them: `Instalar.bat -Models base,anime`
(`all`, `none`), `bash scripts/install.sh --models ...`. Every file is pinned to a
Hugging Face commit and checked against its sha256; files already in place (also
under an older name, see `aliases`) are never downloaded or replaced. Ollama
models are pulled through Ollama, so it must be installed. Licenses are in the
manifest: Flux dev is non-commercial, and re-uploads may not carry the author's
terms. To fetch without the rest of the installer:

```bash
cd animesito && .venv/bin/python ../scripts/fetch_models.py \
  "$(sed -n 's/^JFAST_COMFY_MODELS_DIR=//p' .env)" --groups flux
```

The app itself copies nothing: it asks ComfyUI for its checkpoints (`models/checkpoints`)
and Flux GGUF files (`models/diffusion_models`), and reads each file's header
from `JFAST_COMFY_MODELS_DIR` to detect the family and v-prediction. Video,
inpaint, Kontext and unknown architectures are left out of the selector. To see
the list without starting anything:

```bash
cd animesito && PYTHONPATH=. .venv/bin/python ../scripts/models_report.py \
  "$(sed -n 's/^JFAST_COMFY_MODELS_DIR=//p' .env)"
```
