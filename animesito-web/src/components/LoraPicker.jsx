import { mdiClose, mdiPlus } from '@mdi/js'
import { useState } from 'react'

import BaseButton from '@/components/BaseButton.jsx'
import BaseIcon from '@/components/BaseIcon.jsx'

const SELECT =
  'w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm text-ink focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:outline-none'

// LoRAs with a strength each. The base model a LoRA was trained on is shown
// because v1 silently applied a Krea LoRA to SDXL checkpoints, where it does
// nothing useful.
export default function LoraPicker({ options, value, onChange, maxItems = 6 }) {
  const [pick, setPick] = useState('')
  const chosen = new Set(value.map((item) => item.name))
  const available = options.filter((option) => !chosen.has(option.name))
  const byName = Object.fromEntries(options.map((option) => [option.name, option]))

  function add() {
    if (!pick) return
    onChange([...value, { name: pick, strength: 0.8 }])
    setPick('')
  }

  return (
    <div className="space-y-2">
      {value.map((item, index) => {
        const info = byName[item.name]
        return (
          <div key={item.name} className="rounded-lg border border-line p-2">
            <div className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-xs font-medium" title={item.name}>
                {item.name}
              </span>
              {info?.base_model ? (
                <span className="text-[10px] text-ink-faint">{info.base_model}</span>
              ) : null}
              <button
                type="button"
                className="rounded p-0.5 text-ink-faint hover:bg-elevated hover:text-ink"
                aria-label={`Quitar ${item.name}`}
                onClick={() => onChange(value.filter((_, i) => i !== index))}
              >
                <BaseIcon path={mdiClose} size="sm" />
              </button>
            </div>
            <label className="mt-1 flex items-center gap-2 text-xs text-ink-soft">
              Fuerza
              <input
                type="range"
                min="-1"
                max="2"
                step="0.05"
                value={item.strength}
                className="flex-1 accent-brand-600"
                onChange={(event) =>
                  onChange(
                    value.map((entry, i) =>
                      i === index ? { ...entry, strength: Number(event.target.value) } : entry,
                    ),
                  )
                }
              />
              <span className="w-10 text-right tabular-nums">{Number(item.strength).toFixed(2)}</span>
            </label>
            {info?.trigger_words?.length ? (
              <p className="mt-1 truncate text-[10px] text-ink-faint" title={info.trigger_words.join(', ')}>
                Triggers: {info.trigger_words.join(', ')}
              </p>
            ) : null}
          </div>
        )
      })}
      {value.length < maxItems && available.length > 0 ? (
        <div className="flex gap-2">
          <select
            aria-label="Añadir LoRA"
            className={SELECT}
            value={pick}
            onChange={(event) => setPick(event.target.value)}
          >
            <option value="">Añadir LoRA…</option>
            {available.map((option) => (
              <option key={option.name} value={option.name}>
                {option.name}
                {option.base_model ? ` (${option.base_model})` : ''}
              </option>
            ))}
          </select>
          <BaseButton variant="outline" icon={mdiPlus} aria-label="Añadir" disabled={!pick} onClick={add} />
        </div>
      ) : null}
    </div>
  )
}
