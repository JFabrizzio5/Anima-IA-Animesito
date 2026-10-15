# Engine

Owns the conversation with ComfyUI: the async HTTP/WebSocket client
(`services/comfy_client.py`), the workflow library (`workflows/*.api.json`,
patched by `_meta.title` anchors such as `@ckpt`, `@positive`, `@sampler`) and
the model inspector that reads safetensors headers (v-prediction, LoRA base,
trigger words). It holds no rows. The `comfy` plugin (`plugin.py`) builds one
client per process; other modules use `public.py`.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/engine/status` | ComfyUI reachability, version, VRAM, queue depth |

## Invariants

- Every workflow node the code patches has an anchor; node ids are never hardcoded.
- `tests/test_workflows_live.py` validates every workflow against the real
  `/object_info` when ComfyUI is reachable.
