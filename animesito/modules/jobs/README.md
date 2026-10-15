# Jobs

Owns GPU work from "queued" to "done": the `jobs` table and its state machine
(compare-and-set transitions), the dispatcher that hands ComfyUI one prompt at
a time and turns its WebSocket events into transitions, the `jobs.ingest` queue
task that copies outputs into the gallery, and the SSE stream the browser
listens to. ComfyUI is the GPU queue; the framework queue only runs the short
ingest step, because its claims are not extended for multi-minute renders.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/jobs/events` | Server-sent events (`event: job`) for every change |
| GET | `/jobs` | Recent jobs |
| GET | `/jobs/{id}` | One job |
| POST | `/jobs/{id}/cancel` | Cancel; interrupts or dequeues it in ComfyUI |

## Invariants

- One dispatcher per deployment (Redis lease `animesito:dispatcher`).
- At most one of our prompts is inside ComfyUI at a time.
- A job's events are published after the transaction that changed it commits.
