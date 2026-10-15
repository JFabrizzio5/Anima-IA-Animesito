import { useEffect, useState } from 'react'

import api from '@/services/api.js'

const POLL_MS = 15000

// ComfyUI runs outside this app; say plainly whether it is there, and how much
// VRAM is left, because that decides whether the next render will fit.
export default function EngineStatus() {
  const [status, setStatus] = useState(null)

  useEffect(() => {
    let alive = true
    const load = () =>
      api
        .get('/engine/status')
        .then(({ data }) => alive && setStatus(data))
        .catch(() => alive && setStatus({ reachable: false, detail: 'API no disponible' }))
    load()
    const timer = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])

  if (!status) return null
  const vram =
    status.vram_total_mb && status.vram_free_mb != null
      ? `${(status.vram_free_mb / 1024).toFixed(1)}/${(status.vram_total_mb / 1024).toFixed(0)} GB libres`
      : null

  return (
    <span
      title={status.reachable ? `ComfyUI ${status.version ?? ''} · ${status.device ?? ''}` : status.detail}
      className="hidden items-center gap-2 rounded-full border border-line px-3 py-1 text-xs text-ink-soft sm:inline-flex"
    >
      <span
        className={`size-2 rounded-full ${status.reachable ? 'bg-emerald-500' : 'bg-brand-500'}`}
        aria-hidden="true"
      />
      {status.reachable ? 'ComfyUI en línea' : 'ComfyUI apagado'}
      {status.reachable && vram ? <span className="text-ink-faint">· {vram}</span> : null}
    </span>
  )
}
