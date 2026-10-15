# Assistant

Owns the local LLM (Ollama, running natively on Windows): turning a description
in Spanish or English into Danbooru tags ("Mejorar con IA", v1's enhance flow,
now server-side and policy-checked), the list of models that fit the GPU, and
the VRAM hand-off -- requests use `keep_alive: 0`, and the `jobs.before_submit`
hook evicts any loaded model before the dispatcher hands ComfyUI a prompt.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/assistant/models` | Ollama models that fit the GPU (embeddings excluded) |
| POST | `/assistant/enhance` | Description to Danbooru tags + negative |
