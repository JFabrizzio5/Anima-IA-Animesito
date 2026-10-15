// v1's "Anime Classic" controls: artistic style presets, visible steps/CFG
// sliders, friendly sampler names and the hires fix. Picking a style sets its
// recommended steps, CFG, sampler, size and hires; everything stays editable.

const SELECT =
  'w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm text-ink focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:outline-none'
const LABEL = 'mb-1.5 block text-xs font-medium text-ink-soft'

// A1111 names, as v1 showed them, mapped to ComfyUI sampler + scheduler.
export const FRIENDLY_SAMPLERS = [
  { id: 'euler_a', label: 'Euler a (estándar / rápido)', sampler: 'euler_ancestral', scheduler: 'normal' },
  { id: 'dpm2m_karras', label: 'DPM++ 2M Karras (detallado)', sampler: 'dpmpp_2m', scheduler: 'karras' },
  { id: 'dpm_sde_karras', label: 'DPM++ SDE Karras (realista)', sampler: 'dpmpp_sde', scheduler: 'karras' },
  { id: 'euler', label: 'Euler (limpio, Flux)', sampler: 'euler', scheduler: 'normal' },
]

function groupStyles(styles) {
  const groups = new Map()
  for (const style of styles) {
    if (!groups.has(style.group)) groups.set(style.group, [])
    groups.get(style.group).push(style)
  }
  return [...groups.entries()]
}

export default function ClassicControls({ form, patch, model, styles }) {
  const steps = form.steps ?? model?.steps ?? 28
  const cfg = form.cfg ?? model?.cfg ?? 6
  const sampler = form.sampler ?? model?.sampler
  const scheduler = form.scheduler ?? model?.scheduler
  const friendly = FRIENDLY_SAMPLERS.find((item) => item.sampler === sampler && item.scheduler === scheduler)
  const isFlux = model?.supports_negative === false

  function pickStyle(id) {
    const style = styles.find((item) => item.id === id)
    if (!style) {
      patch({ style: null, steps: null, cfg: null, sampler: null, scheduler: null, hires: false })
      return
    }
    patch({
      style: style.id,
      steps: style.steps,
      cfg: style.cfg,
      sampler: style.sampler,
      scheduler: style.scheduler,
      hires: style.hires && !isFlux,
      ...(style.width && style.height ? { width: style.width, height: style.height } : {}),
    })
  }

  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="style" className={LABEL}>
          Estilo artístico (preconfiguraciones)
        </label>
        <select id="style" className={SELECT} value={form.style ?? ''} onChange={(event) => pickStyle(event.target.value)}>
          <option value="">Sin estilo · tags de calidad del modelo</option>
          {groupStyles(styles).map(([group, items]) => (
            <optgroup key={group} label={group}>
              {items.map((style) => (
                <option key={style.id} value={style.id}>
                  {style.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        {form.style ? (
          <p className="mt-1 truncate text-[11px] text-ink-faint" title={styles.find((item) => item.id === form.style)?.pos}>
            + {styles.find((item) => item.id === form.style)?.pos}
          </p>
        ) : null}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className={LABEL}>
            Pasos (steps): <span className="text-ink">{steps}</span>
          </span>
          <input type="range" min="8" max="60" step="1" value={steps} className="w-full accent-brand-600" onChange={(event) => patch({ steps: Number(event.target.value) })} />
        </label>
        <label className="block">
          <span className={LABEL}>
            {isFlux ? 'Guidance (Flux)' : 'CFG scale'}: <span className="text-ink">{cfg}</span>
          </span>
          <input type="range" min="1" max="12" step="0.5" value={cfg} className="w-full accent-brand-600" onChange={(event) => patch({ cfg: Number(event.target.value) })} />
        </label>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="friendly-sampler" className={LABEL}>
            Sampler
          </label>
          <select
            id="friendly-sampler"
            className={SELECT}
            value={friendly?.id ?? ''}
            onChange={(event) => {
              const item = FRIENDLY_SAMPLERS.find((entry) => entry.id === event.target.value)
              patch(item ? { sampler: item.sampler, scheduler: item.scheduler } : { sampler: null, scheduler: null })
            }}
          >
            <option value="">{friendly ? 'Auto (modelo)' : `Auto / avanzado (${sampler ?? '—'} · ${scheduler ?? '—'})`}</option>
            {FRIENDLY_SAMPLERS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="hires" className={LABEL}>
            Hires fix (upscale ×1.5)
          </label>
          <select
            id="hires"
            className={SELECT}
            value={form.hires && !isFlux ? 'on' : 'off'}
            disabled={isFlux}
            onChange={(event) => patch({ hires: event.target.value === 'on' })}
          >
            <option value="off">Desactivado (rápido)</option>
            <option value="on">Activado (más calidad, más lento)</option>
          </select>
          {isFlux ? <p className="mt-1 text-[11px] text-ink-faint">No disponible con Flux.</p> : null}
        </div>
      </div>
    </div>
  )
}
