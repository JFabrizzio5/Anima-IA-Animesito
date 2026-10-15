"""Which local models Animesito will offer, decided the way the app decides.

The running app gets its model lists from ComfyUI; this reads the same folders
directly, so the installer can show the result before anything is started.

    cd animesito && PYTHONPATH=. .venv/bin/python ../scripts/models_report.py MODELS_DIR
"""

from __future__ import annotations

import json
import sys
import tomllib
import urllib.request
from pathlib import Path

from modules.assistant.services.ollama_client import LlmModel
from modules.engine.public import ModelTraits
from modules.engine.services.model_inspector import read_traits
from modules.generation.services.profiles import CKPT, GGUF, resolve

OLLAMA_TAGS = "http://127.0.0.1:11434/api/tags"
JFAST_TOML = Path(__file__).resolve().parent.parent / "animesito" / "jfast.toml"


def _files(root: Path, folder: str, suffix: str) -> list[tuple[str, Path]]:
    base = root / folder
    if not base.is_dir():
        return []
    return [(path.relative_to(base).as_posix(), path) for path in sorted(base.rglob(f"*{suffix}"))]


def image_models(root: Path) -> None:
    print(f"ComfyUI models in {root}")
    if not root.is_dir():
        print("  folder not found")
        return
    rows = [
        (name, resolve(CKPT, name, read_traits(path)))
        for name, path in _files(root, "checkpoints", ".safetensors")
    ]
    for folder in ("diffusion_models", "unet"):
        rows += [
            (name, resolve(GGUF, name, ModelTraits())) for name, _ in _files(root, folder, ".gguf")
        ]
    for name, choice in rows:
        if choice is None:
            print(f"  -  {name}  (not a txt2img model the app drives)")
        else:
            vpred = ", v-pred" if choice.v_prediction else ""
            print(f"  +  {name}  [{choice.profile.label}{vpred}]")
    for name, path in _files(root, "loras", ".safetensors"):
        print(f"  lora  {name}  (base: {read_traits(path).base_model or 'unknown'})")


def llm_models() -> None:
    max_gb = tomllib.loads(JFAST_TOML.read_text())["plugin"]["assistant"]["max_model_gb"]
    try:
        with urllib.request.urlopen(OLLAMA_TAGS, timeout=3) as response:
            items = json.load(response).get("models", [])
    except OSError:
        print("Ollama: not running, models not listed (Iniciar.bat starts it)")
        return
    print('Ollama models ("Mejorar con IA")')
    for item in items:
        model = LlmModel(
            name=str(item.get("name")),
            size_bytes=int(item.get("size") or 0),
            parameter_size=(item.get("details") or {}).get("parameter_size"),
            capabilities=tuple(item.get("capabilities") or ()),
        )
        # Same filter as GET /assistant/models.
        hidden = None
        if model.is_embedding:
            hidden = "embedding model"
        elif model.is_reasoning:
            hidden = "reasoning model"
        elif model.size_gb > max_gb:
            hidden = f"over {max_gb} GB"
        print(
            f"  {'-' if hidden else '+'}  {model.name}  {model.size_gb} GB"
            + (f"  (hidden: {hidden})" if hidden else "")
        )


if __name__ == "__main__":
    image_models(Path(sys.argv[1]) if len(sys.argv) > 1 else Path())
    print()
    llm_models()
