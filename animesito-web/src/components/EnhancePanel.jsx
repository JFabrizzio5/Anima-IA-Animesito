import { mdiCreationOutline } from '@mdi/js'
import { useEffect, useState } from 'react'

import BaseButton from '@/components/BaseButton.jsx'
import { toast } from '@/hooks/useToast.js'
import api from '@/services/api.js'

const SELECT =
  'rounded-lg border border-line bg-panel px-2 py-1.5 text-xs text-ink focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:outline-none'

// v1's "Mejorar prompt": describe it in Spanish, get Danbooru tags back. Runs
// on Ollama locally; the server frees ComfyUI's VRAM first when it is idle.
export default function EnhancePanel({ prompt, adult, onApply }) {
  const [models, setModels] = useState(null)
  const [model, setModel] = useState('')
  const [busy, setBusy] = useState(false)
  const [suggestion, setSuggestion] = useState(null)

  useEffect(() => {
    api
      .get('/assistant/models')
      .then(({ data }) => {
        setModels(data)
        setModel(data.models.some((item) => item.name === data.default) ? data.default : (data.models[0]?.name ?? ''))
      })
      .catch(() => setModels({ models: [], reachable: false }))
  }, [])

  async function run() {
    setBusy(true)
    setSuggestion(null)
    try {
      const { data } = await api.post('/assistant/enhance', { prompt, adult, model: model || undefined }, { timeout: 240000 })
      setSuggestion(data)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (models && !models.reachable) {
    return <p className="text-xs text-ink-faint">Ollama no está corriendo: "Mejorar con IA" no disponible.</p>
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <BaseButton size="sm" variant="outline" icon={mdiCreationOutline} loading={busy} disabled={prompt.trim().length < 2 || !model} onClick={run}>
          Mejorar con IA
        </BaseButton>
        <select aria-label="Modelo de lenguaje" className={SELECT} value={model} onChange={(event) => setModel(event.target.value)}>
          {(models?.models ?? []).map((item) => (
            <option key={item.name} value={item.name}>
              {item.name} · {item.size_gb} GB
            </option>
          ))}
        </select>
        {busy ? <span className="text-xs text-ink-faint">~10 s · convierte tu descripción a tags</span> : null}
      </div>
      {suggestion ? (
        <div className="rounded-lg border border-brand-300 p-2 text-xs dark:border-brand-800">
          <p className="break-words text-ink">{suggestion.prompt}</p>
          {suggestion.negative ? <p className="mt-1 break-words text-ink-faint">Negativo: {suggestion.negative}</p> : null}
          <p className="mt-1 text-[10px] text-ink-faint">
            {suggestion.model} · {suggestion.seconds} s
          </p>
          <div className="mt-2 flex gap-2">
            <BaseButton
              size="sm"
              onClick={() => {
                onApply(suggestion)
                setSuggestion(null)
              }}
            >
              Aplicar
            </BaseButton>
            <BaseButton size="sm" variant="ghost" onClick={() => setSuggestion(null)}>
              Descartar
            </BaseButton>
          </div>
        </div>
      ) : null}
    </div>
  )
}
