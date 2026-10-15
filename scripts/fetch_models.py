"""Fetch the models Animesito uses: ComfyUI files, custom nodes, Ollama models.

    cd animesito && .venv/bin/python ../scripts/fetch_models.py MODELS_DIR [--groups SETS]

SETS is a comma list of the groups in scripts/models.toml, 'all' or 'none'.

Driven by scripts/models.toml. Without --groups it asks when run in a terminal
and takes the default groups otherwise. Only what is missing is fetched: a file
is written to <name>.part, resumed from there after an interruption, and
renamed only once its size and sha256 match the manifest. Set HF_TOKEN for a
Hugging Face repo that needs a login.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import zipfile
from pathlib import Path
from typing import Any

import httpx

MANIFEST = Path(__file__).resolve().with_name("models.toml")
OLLAMA_URL = "http://127.0.0.1:11434"
CHUNK = 8 * 1024 * 1024
RETRIES = 5
GB = 1024**3
#: Left free on the disk after the downloads.
MARGIN = 2 * GB
TTY = sys.stdout.isatty()


class FetchError(RuntimeError):
    """One item could not be installed; the others still are."""


class Retry(RuntimeError):
    """A transient failure: resume the download from what is on disk."""


def human(size: float) -> str:
    return f"{size / GB:.1f} GB"


class Progress:
    def __init__(self, label: str, total: int) -> None:
        self.label, self.total = label, total
        self.started = self.shown = time.monotonic()
        self.first: int | None = None

    def update(self, done: int) -> None:
        now = time.monotonic()
        if self.first is None:
            # The rate counts from here, so a resumed file does not look fast.
            self.first, self.started, self.shown = done, now, now
            return
        if now - self.shown < (1 if TTY else 30):
            return
        self.shown = now
        rate = (done - self.first) / (now - self.started) / 1024**2
        line = f"  {self.label}  {human(done)} / {human(self.total)}  {rate:.0f} MB/s"
        print(f"\r{line:<100}" if TTY else line, end="" if TTY else "\n", flush=True)

    def finish(self) -> None:
        if TTY:
            print()


def _hash_file(path: Path) -> tuple[Any, int]:
    digest, size = hashlib.sha256(), 0
    if path.exists():
        with path.open("rb") as handle:
            while chunk := handle.read(CHUNK):
                digest.update(chunk)
                size += len(chunk)
    return digest, size


def _auth() -> dict[str, str]:
    token = os.environ.get("HF_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def present(root: Path, item: dict[str, Any]) -> Path | None:
    for name in (item["file"], *item.get("aliases", ())):
        path = root / item["folder"] / name
        if path.is_file():
            return path
    return None


def download(root: Path, item: dict[str, Any]) -> None:
    target = root / item["folder"] / item["file"]
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    size = item["size"]
    digest, hashed = _hash_file(part)  # a resumed .part is hashed once, here
    if hashed > size:
        part.unlink()
        digest, hashed = hashlib.sha256(), 0
    progress = Progress(item["file"], size)
    for attempt in range(1, RETRIES + 1):
        if hashed == size:
            break
        request_headers = _auth() | ({"Range": f"bytes={hashed}-"} if hashed else {})
        try:
            with httpx.stream(
                "GET",
                item["url"],
                headers=request_headers,
                follow_redirects=True,
                timeout=httpx.Timeout(30.0, read=120.0),
            ) as response:
                if response.status_code in (401, 403):
                    raise FetchError(
                        f"{item['file']}: HTTP {response.status_code}, "
                        "the repo needs a login (set HF_TOKEN)"
                    )
                if response.status_code >= 500:
                    raise Retry(f"HTTP {response.status_code}")
                if response.status_code not in (200, 206):
                    raise FetchError(
                        f"{item['file']}: HTTP {response.status_code} from {item['url']}"
                    )
                if response.status_code == 200 and hashed:
                    # The server ignored the range: start over.
                    digest, hashed = hashlib.sha256(), 0
                with part.open("ab" if hashed else "wb") as handle:
                    for chunk in response.iter_bytes(CHUNK):
                        handle.write(chunk)
                        digest.update(chunk)
                        hashed += len(chunk)
                        progress.update(hashed)
        except (httpx.TransportError, Retry) as exc:
            if attempt == RETRIES:
                progress.finish()
                raise FetchError(f"{item['file']}: {exc} (run again to resume)") from exc
            print(f"\n  {item['file']}: {exc}; resuming in {attempt * 5} s", flush=True)
            time.sleep(attempt * 5)
    progress.finish()
    if hashed != size or digest.hexdigest() != item["sha256"]:
        part.unlink(missing_ok=True)
        raise FetchError(
            f"{item['file']}: size or sha256 does not match the manifest; "
            "the partial file was removed"
        )
    part.rename(target)
    print(f"  ok  {item['file']}  (sha256 verified)")


def comfy_python(comfy: Path) -> Path | None:
    for candidate in (
        comfy / "venv" / "Scripts" / "python.exe",
        comfy.parent / "python_embeded" / "python.exe",  # the portable build
        comfy / ".venv" / "Scripts" / "python.exe",
    ):
        if candidate.is_file():
            return candidate
    return None


def windows_path(path: Path) -> str:
    return subprocess.run(
        ["wslpath", "-w", str(path)], check=True, capture_output=True, text=True
    ).stdout.strip()


def install_node(comfy: Path, node: dict[str, Any]) -> None:
    target = comfy / "custom_nodes" / node["name"]
    response = httpx.get(node["url"], follow_redirects=True, timeout=60.0)
    if response.status_code != 200:
        raise FetchError(f"{node['name']}: HTTP {response.status_code} from {node['url']}")
    with tempfile.TemporaryDirectory() as scratch:
        archive_path = Path(scratch) / "node.zip"
        archive_path.write_bytes(response.content)
        with zipfile.ZipFile(archive_path) as archive:
            top = archive.namelist()[0].split("/")[0]
            archive.extractall(scratch)
        shutil.move(str(Path(scratch) / top), target)
    requirements = target / "requirements.txt"
    python = comfy_python(comfy)
    if requirements.is_file() and python is None:
        raise FetchError(
            f"{node['name']}: unpacked, but ComfyUI's Python was not found "
            f"to install {requirements.name}"
        )
    if requirements.is_file():
        result = subprocess.run(
            [str(python), "-m", "pip", "install", "-r", windows_path(requirements)]
        )
        if result.returncode != 0:
            raise FetchError(f"{node['name']}: pip install -r requirements.txt failed")
    print(f"  ok  {node['name']} (restart ComfyUI to load it)")


def ollama_installed() -> set[str] | None:
    try:
        response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3.0)
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    return {model["name"] for model in response.json().get("models", [])}


def ollama_pull(model: dict[str, Any]) -> None:
    progress = Progress(model["name"], model["size"])
    try:
        with httpx.stream(
            "POST",
            f"{OLLAMA_URL}/api/pull",
            json={"model": model["name"]},
            timeout=httpx.Timeout(30.0, read=600.0),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                event = json.loads(line) if line.strip() else {}
                if "error" in event:
                    raise FetchError(f"{model['name']}: {event['error']}")
                if event.get("total") and event.get("completed") is not None:
                    progress.total = event["total"]
                    progress.update(event["completed"])
    except httpx.HTTPError as exc:
        raise FetchError(f"{model['name']}: {exc}") from exc
    finally:
        progress.finish()
    print(f"  ok  {model['name']}")


def choose_groups(
    manifest: dict[str, Any], requested: str | None, missing: dict[str, int], total: dict[str, int]
) -> list[str]:
    names = list(manifest["groups"])
    default = ",".join(name for name, group in manifest["groups"].items() if group.get("default"))
    if requested is None and sys.stdin.isatty():
        print("Model sets  (still to download / total)")
        for name, group in manifest["groups"].items():
            sizes = f"{human(missing[name]):>8} / {human(total[name]):<8}"
            print(f"  {name:<10} {sizes}  {group['label']}")
        requested = (
            input(f"Which sets? Comma list, 'all' or 'none' [{default}]: ").strip() or default
        )
    requested = default if requested is None else requested
    if requested == "all":
        return names
    if requested == "none":
        return []
    chosen = [name.strip() for name in requested.split(",") if name.strip()]
    unknown = [name for name in chosen if name not in names]
    if unknown:
        raise FetchError(
            f"unknown model set(s): {', '.join(unknown)}. "
            f"Choose from: {', '.join(names)}, all, none"
        )
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch the models Animesito uses.")
    parser.add_argument(
        "models_dir", type=Path, help="ComfyUI's models folder, as this system sees it"
    )
    parser.add_argument("--groups", help="comma list of model sets, 'all' or 'none'")
    args = parser.parse_args()

    manifest = tomllib.loads(MANIFEST.read_text())
    root: Path = args.models_dir
    if not (root / "checkpoints").is_dir():
        raise FetchError(
            f"{root} is not a ComfyUI models folder (no checkpoints/). Install ComfyUI first."
        )
    comfy = root.parent
    llms_installed = ollama_installed()

    files = manifest.get("files", [])
    nodes = manifest.get("nodes", [])
    llms = manifest.get("ollama", [])
    missing = dict.fromkeys(manifest["groups"], 0)
    total = dict.fromkeys(manifest["groups"], 0)
    for item in files:
        total[item["group"]] += item["size"]
        missing[item["group"]] += 0 if present(root, item) else item["size"]
    for model in llms:
        total[model["group"]] += model["size"]
        missing[model["group"]] += (
            0 if llms_installed and model["name"] in llms_installed else model["size"]
        )

    groups = choose_groups(manifest, args.groups, missing, total)
    if not groups:
        print("No model sets chosen.")
        return 0
    print(f"Model sets: {', '.join(groups)}")

    to_download = []
    for item in (item for item in files if item["group"] in groups):
        found = present(root, item)
        if found is None:
            to_download.append(item)
        elif found.stat().st_size != item["size"]:
            print(f"  kept  {found.name}  (a different file than the pinned one; not replaced)")
        else:
            print(f"  have  {found.name}")
    to_install = [
        node
        for node in nodes
        if node["group"] in groups and not (comfy / "custom_nodes" / node["name"]).is_dir()
    ]
    for node in (node for node in nodes if node["group"] in groups and node not in to_install):
        print(f"  have  custom node {node['name']}")
    to_pull = [
        model
        for model in llms
        if model["group"] in groups and not (llms_installed and model["name"] in llms_installed)
    ]
    for model in (model for model in llms if model["group"] in groups and model not in to_pull):
        print(f"  have  ollama {model['name']}")

    need = sum(item["size"] for item in to_download)
    free = shutil.disk_usage(root).free
    if need + MARGIN > free:
        raise FetchError(
            f"needs {human(need)} plus {human(MARGIN)} free in {root}, there is {human(free)}"
        )
    if to_download:
        print(f"Downloading {len(to_download)} file(s), {human(need)}:")
        for item in to_download:
            path = f"{item['folder']}/{item['file']}"
            print(f"  {path}  {human(item['size'])}  license: {item['license']}")

    failures: list[str] = []
    for item in to_download:
        try:
            download(root, item)
        except FetchError as exc:
            failures.append(str(exc))
            print(f"  FAILED  {exc}")
    for node in to_install:
        try:
            install_node(comfy, node)
        except FetchError as exc:
            failures.append(str(exc))
            print(f"  FAILED  {exc}")
    if to_pull and llms_installed is None:
        failures.append(
            "Ollama is not running, so its models were not pulled: start Ollama and run again"
        )
        print(f"  FAILED  {failures[-1]}")
    elif to_pull:
        for model in to_pull:
            try:
                ollama_pull(model)
            except FetchError as exc:
                failures.append(str(exc))
                print(f"  FAILED  {exc}")

    if failures:
        print(f"\n{len(failures)} item(s) not installed; running the installer again resumes them.")
        return 1
    print("All chosen models are installed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted: run again to resume from the .part files.")
        sys.exit(130)
