# Generation

Owns the translation from "what the user asked for" to "the ComfyUI graphs that
produce it": model families and their prompting/sampling defaults
(`profiles.toml`, ported from v1's `enrichCkptPrompt`), prompt composition
(quality → rating → subject, then the policy module's checks), graph building
on the engine's workflow library (LoRA chain, v-prediction for v-pred
checkpoints detected from their header), batching and seeds. It queues jobs
through `modules/jobs/public.py` and owns no table.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/generate/options` | Installed models (by family), LoRAs, samplers, schedulers, size presets |
| POST | `/generate/image` | Queue txt2img jobs (one per batch); returns job ids and the final prompt |

## Invariants

- Model, LoRA, sampler and scheduler names are checked against ComfyUI's own
  `/object_info` before anything is queued.
- Every positive prompt passes `policy.check_prompt`.
