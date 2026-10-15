import { mdiDiceMultipleOutline, mdiImageMultipleOutline, mdiPlay } from '@mdi/js'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import BaseButton from '@/components/BaseButton.jsx'
import CardBox from '@/components/CardBox.jsx'
import ClassicControls from '@/components/ClassicControls.jsx'
import EmptyState from '@/components/EmptyState.jsx'
import EnhancePanel from '@/components/EnhancePanel.jsx'
import LoraPicker from '@/components/LoraPicker.jsx'
import PromptBuilder from '@/components/PromptBuilder.jsx'
import { toast } from '@/hooks/useToast.js'
import api from '@/services/api.js'
import { finalPrompt, useBuilder } from '@/stores/builder.store.js'
import { useImageForm } from '@/stores/imageForm.store.js'
import { useJobsStore } from '@/stores/jobs.store.js'

const FIELD =
  'w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:outline-none'
const LABEL = 'mb-1.5 block text-xs font-medium text-ink-soft'
const MAX_SEED = 2 ** 53 - 1

function Field({ label, htmlFor, children, className = '' }) {
  return (
    <div className={className}>
      <label htmlFor={htmlFor} className={LABEL}>
        {label}
      </label>
      {children}
    </div>
  )
}

function NumberInput({ id, value, onChange, placeholder, min, max, step = 1 }) {
  return (
    <input
      id={id}
      type="number"
      className={FIELD}
      value={value ?? ''}
      placeholder={placeholder}
      min={min}
      max={max}
      step={step}
      onChange={(event) => onChange(event.target.value === '' ? null : Number(event.target.value))}
    />
  )
}

export default function ImageView() {
  const form = useImageForm((state) => state.form)
  const setField = useImageForm((state) => state.setField)
  const patch = useImageForm((state) => state.patch)
  const [options, setOptions] = useState(null)
  const [loadingOptions, setLoadingOptions] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [lastPrompt, setLastPrompt] = useState(null)
  const [results, setResults] = useState([])
  const mine = useRef(new Set())
  const jobs = useJobsStore((state) => state.jobs)
  const onJob = useJobsStore((state) => state.onJob)

  const loadOptions = useCallback(() => {
    setLoadingOptions(true)
    api
      .get('/generate/options')
      .then(({ data }) => setOptions(data))
      .catch((err) => toast.error(err.message))
      .finally(() => setLoadingOptions(false))
  }, [])

  useEffect(loadOptions, [loadOptions])

  // Pick a model when none (or a removed one) is selected.
  useEffect(() => {
    if (!options?.models?.length) return
    if (!options.models.some((model) => model.id === form.model)) {
      setField('model', options.models[0].id)
    }
  }, [options, form.model, setField])

  // When one of the jobs started here finishes, fetch its images.
  useEffect(
    () =>
      onJob((job) => {
        if (!mine.current.has(job.id) || job.status !== 'done') return
        mine.current.delete(job.id)
        Promise.all(job.result_ids.map((id) => api.get(`/gallery/${id}`).then(({ data }) => data)))
          .then((items) => setResults((previous) => [...items, ...previous].slice(0, 48)))
          .catch((err) => toast.error(err.message))
      }),
    [onJob],
  )

  const model = useMemo(
    () => options?.models?.find((item) => item.id === form.model) ?? null,
    [options, form.model],
  )
  const families = useMemo(() => {
    const groups = new Map()
    for (const item of options?.models ?? []) {
      if (!groups.has(item.family_label)) groups.set(item.family_label, [])
      groups.get(item.family_label).push(item)
    }
    return [...groups.entries()]
  }, [options])

  // Whole state, not a selector: compose() returns a new object every call,
  // and a selector returning one would re-render forever.
  const builder = useBuilder()
  const built = builder.enabled ? builder.compose() : { scene: '', characters: [] }
  const promptToSend = finalPrompt(built.scene, form.prompt)
  const characterPrompts = built.characters

  const pending = [...mine.current].map((id) => jobs[id]).filter(Boolean)

  async function submit(event) {
    event?.preventDefault()
    if (!promptToSend || !form.model) return
    setSubmitting(true)
    try {
      const { data } = await api.post('/generate/image', {
        ...form,
        prompt: promptToSend,
        character_prompts: characterPrompts,
        layout: builder.layout,
        style: form.style || null,
        hires: Boolean(form.hires) && model?.supports_negative !== false,
        negative: model?.supports_negative ? form.negative : '',
      })
      data.jobs.forEach((job) => {
        mine.current.add(job.id)
        useJobsStore.getState().upsert({ ...job, progress: 0, progress_text: 'En cola', kind: 'image', result_ids: [] })
      })
      setLastPrompt({ positive: data.prompt, negative: data.negative })
      toast.success(`${data.jobs.length} trabajo(s) en cola`)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  function onKeyDown(event) {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) submit(event)
  }

  if (!loadingOptions && options && !options.engine_reachable) {
    return (
      <div className="p-6">
        <CardBox>
          <EmptyState
            icon={mdiImageMultipleOutline}
            title="ComfyUI no está corriendo"
            description="Arranca ComfyUI (Iniciar.bat lo hace por ti) y vuelve a intentar. La galería sigue disponible mientras tanto."
          >
            <BaseButton onClick={loadOptions}>Reintentar</BaseButton>
          </EmptyState>
        </CardBox>
      </div>
    )
  }

  return (
    <div className="grid gap-6 p-4 md:p-6 xl:grid-cols-[26rem_1fr]">
      <form onSubmit={submit} onKeyDown={onKeyDown} className="space-y-4">
        <CardBox className="space-y-4 !p-4">
          <Field label="Modelo" htmlFor="model">
            <select
              id="model"
              className={FIELD}
              value={form.model}
              disabled={loadingOptions}
              onChange={(event) => patch({ model: event.target.value, steps: null, cfg: null, sampler: null, scheduler: null })}
            >
              {families.map(([label, models]) => (
                <optgroup key={label} label={label}>
                  {models.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                      {item.v_prediction ? ' · v-pred' : ''}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </Field>

          <Field label="Prompt" htmlFor="prompt">
            <textarea
              id="prompt"
              rows={5}
              className={FIELD}
              placeholder="1girl, silver hair, rooftop at night, city lights…"
              value={form.prompt}
              onChange={(event) => setField('prompt', event.target.value)}
            />
          </Field>

          <EnhancePanel
            prompt={form.prompt}
            adult={form.adult}
            onApply={(suggestion) =>
              patch({
                prompt: suggestion.prompt,
                negative: [form.negative, suggestion.negative].filter(Boolean).join(', '),
              })
            }
          />

          {model?.supports_negative !== false ? (
            <Field label="Prompt negativo (opcional)" htmlFor="negative">
              <textarea
                id="negative"
                rows={2}
                className={FIELD}
                value={form.negative}
                onChange={(event) => setField('negative', event.target.value)}
              />
            </Field>
          ) : null}

          <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                className="accent-brand-600"
                checked={form.quality_tags}
                onChange={(event) => setField('quality_tags', event.target.checked)}
              />
              Tags de calidad del modelo
            </label>
            <label className="flex items-center gap-2" title="Solo personajes adultos ficticios. Se bloquean menores.">
              <input
                type="checkbox"
                className="accent-brand-600"
                checked={form.adult}
                onChange={(event) => setField('adult', event.target.checked)}
              />
              Contenido adulto (+18)
            </label>
          </div>
        </CardBox>

        <CardBox className="!p-4">
          <details open>
            <summary className="cursor-pointer text-sm font-medium">
              Constructor de prompt <span className="text-xs font-normal text-ink-faint">· personajes, zonas, tags</span>
            </summary>
            <div className="mt-4">
              <PromptBuilder adult={form.adult} />
            </div>
          </details>
        </CardBox>

        <CardBox className="space-y-4 !p-4">
          <ClassicControls form={form} patch={patch} model={model} styles={options?.styles ?? []} />

          <div>
            <p className={LABEL}>Tamaño</p>
            <div className="flex flex-wrap gap-1.5">
              {(options?.sizes ?? []).map((size) => {
                const active = size.width === form.width && size.height === form.height
                return (
                  <button
                    key={size.label}
                    type="button"
                    onClick={() => patch({ width: size.width, height: size.height })}
                    className={`rounded-md border px-2 py-1 text-xs ${
                      active ? 'border-brand-500 bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300' : 'border-line text-ink-soft hover:bg-elevated'
                    }`}
                  >
                    {size.label}
                  </button>
                )
              })}
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <NumberInput id="width" value={form.width} min={256} max={2048} step={64} onChange={(value) => setField('width', value ?? 832)} />
              <NumberInput id="height" value={form.height} min={256} max={2048} step={64} onChange={(value) => setField('height', value ?? 1216)} />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <Field label="Imágenes" htmlFor="count">
              <NumberInput id="count" value={form.count} min={1} max={16} onChange={(value) => setField('count', value ?? 1)} />
            </Field>
            <Field label="Por lote" htmlFor="batch">
              <NumberInput id="batch" value={form.batch_size} min={1} max={4} onChange={(value) => setField('batch_size', value ?? 1)} />
            </Field>
            <Field label="Semilla" htmlFor="seed">
              <div className="flex gap-1">
                <NumberInput id="seed" value={form.seed} min={-1} max={MAX_SEED} onChange={(value) => setField('seed', value ?? -1)} />
                <BaseButton
                  variant="ghost"
                  icon={mdiDiceMultipleOutline}
                  aria-label="Semilla aleatoria"
                  title="Aleatoria (-1)"
                  onClick={() => setField('seed', -1)}
                />
              </div>
            </Field>
          </div>

          <details className="group">
            <summary className="cursor-pointer text-xs font-medium text-ink-soft">Avanzado</summary>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Field label="Pasos" htmlFor="steps">
                <NumberInput id="steps" value={form.steps} placeholder={String(model?.steps ?? '')} min={1} max={150} onChange={(value) => setField('steps', value)} />
              </Field>
              <Field label={model?.supports_negative === false ? 'Guidance (Flux)' : 'CFG'} htmlFor="cfg">
                <NumberInput id="cfg" value={form.cfg} placeholder={String(model?.cfg ?? '')} min={0} max={30} step={0.5} onChange={(value) => setField('cfg', value)} />
              </Field>
              <Field label="Sampler" htmlFor="sampler">
                <select id="sampler" className={FIELD} value={form.sampler ?? ''} onChange={(event) => setField('sampler', event.target.value || null)}>
                  <option value="">Auto ({model?.sampler ?? '—'})</option>
                  {(options?.samplers ?? []).map((name) => (
                    <option key={name}>{name}</option>
                  ))}
                </select>
              </Field>
              <Field label="Scheduler" htmlFor="scheduler">
                <select id="scheduler" className={FIELD} value={form.scheduler ?? ''} onChange={(event) => setField('scheduler', event.target.value || null)}>
                  <option value="">Auto ({model?.scheduler ?? '—'})</option>
                  {(options?.schedulers ?? []).map((name) => (
                    <option key={name}>{name}</option>
                  ))}
                </select>
              </Field>
            </div>
          </details>

          <div>
            <p className={LABEL}>LoRAs</p>
            <LoraPicker options={options?.loras ?? []} value={form.loras} onChange={(value) => setField('loras', value)} />
          </div>
        </CardBox>

        <div className="rounded-lg border border-line p-3 text-xs">
          <p className="mb-1 font-medium text-ink-soft">Prompt que se enviará</p>
          <p className="break-words text-ink">{promptToSend || <span className="text-ink-faint">Vacío: escribe un prompt o usa el constructor</span>}</p>
          {characterPrompts.map((text, index) => (
            <p key={index} className="mt-1 break-words text-ink">
              <span className="text-ink-faint">Personaje #{index + 1} ({builder.layout === 'columns' ? 'columna' : 'BREAK'}):</span> {text}
            </p>
          ))}
          <p className="mt-1 text-[10px] text-ink-faint">El modelo añade sus tags de calidad; la policy revisa todo antes de encolar.</p>
        </div>

        <BaseButton type="submit" icon={mdiPlay} loading={submitting} disabled={!promptToSend || !form.model} className="w-full">
          Generar <span className="ml-1 text-xs opacity-70">Ctrl+Enter</span>
        </BaseButton>

        {lastPrompt ? (
          <details className="rounded-lg border border-line p-3 text-xs text-ink-soft">
            <summary className="cursor-pointer font-medium">Prompt final enviado</summary>
            <p className="mt-2 break-words text-ink">{lastPrompt.positive}</p>
            {lastPrompt.negative ? <p className="mt-2 break-words">Negativo: {lastPrompt.negative}</p> : null}
          </details>
        ) : null}
      </form>

      <section aria-label="Resultados" className="min-w-0">
        {pending.length === 0 && results.length === 0 ? (
          <CardBox>
            <EmptyState
              icon={mdiImageMultipleOutline}
              title="Aún no hay resultados en esta sesión"
              description="Escribe un prompt y pulsa Generar. Todo lo generado queda también en la Galería."
            />
          </CardBox>
        ) : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-4">
            {pending.map((job) => (
              <div key={job.id} className="flex aspect-[2/3] flex-col items-center justify-center rounded-xl border border-dashed border-line bg-panel p-4 text-center">
                <div className="h-1 w-3/4 overflow-hidden rounded-full bg-elevated">
                  <div className="h-full bg-brand-500 transition-[width] duration-300" style={{ width: `${Math.round(job.progress * 100)}%` }} />
                </div>
                <p className="mt-2 text-xs text-ink-faint">{job.status === 'error' ? job.error : job.progress_text}</p>
              </div>
            ))}
            {results.map((item) => (
              <a key={item.id} href={item.url} target="_blank" rel="noreferrer" className="group overflow-hidden rounded-xl border border-line bg-panel">
                <img src={item.thumb_url ?? item.url} alt={item.prompt} loading="lazy" className="aspect-[2/3] w-full object-cover transition-transform duration-200 group-hover:scale-[1.02]" />
              </a>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
