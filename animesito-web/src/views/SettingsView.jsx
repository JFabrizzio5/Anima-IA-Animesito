import { mdiContentSaveOutline, mdiRestore } from '@mdi/js'
import { useEffect, useState } from 'react'

import BaseButton from '@/components/BaseButton.jsx'
import CardBox from '@/components/CardBox.jsx'
import { toast } from '@/hooks/useToast.js'
import api from '@/services/api.js'
import { splitTags } from '@/stores/builder.store.js'

const FIELD =
  'w-full rounded-lg border border-line bg-panel px-3 py-2 text-xs text-ink placeholder:text-ink-faint focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:outline-none'
const LABEL = 'mb-1 block text-xs font-medium text-ink-soft'

function ReadOnlyList({ title, items }) {
  return (
    <details className="rounded-lg border border-line p-2">
      <summary className="cursor-pointer text-xs font-medium text-ink-soft">
        {title} <span className="font-normal text-ink-faint">({items.length}, solo lectura)</span>
      </summary>
      <div className="mt-2 flex flex-wrap gap-1">
        {items.length ? (
          items.map((item) => (
            <span key={item} className="rounded-full border border-line px-2 py-0.5 text-[11px] text-ink-soft">
              {item}
            </span>
          ))
        ) : (
          <span className="text-[11px] text-ink-faint">Vacía</span>
        )}
      </div>
    </details>
  )
}

// Negatives per model family, a global negative, and the content policy:
// base lists shown read-only, additions editable. Additions only tighten.
export default function SettingsView() {
  const [data, setData] = useState(null)
  const [draft, setDraft] = useState(null)
  const [saving, setSaving] = useState(false)

  function load(fresh) {
    setData(fresh)
    setDraft({
      global_negative: fresh.global_negative,
      family_negatives: Object.fromEntries(
        fresh.families.map((item) => [item.family, { negative: item.negative ?? '', safe_negative: item.safe_negative ?? '' }]),
      ),
      extra_terms: fresh.policy.extra_terms.join(', '),
      extra_characters: fresh.policy.extra_characters.join(', '),
      extra_negative: fresh.policy.extra_negative,
    })
  }

  useEffect(() => {
    api
      .get('/generate/settings')
      .then(({ data: fresh }) => load(fresh))
      .catch((err) => toast.error(err.message))
  }, [])

  async function save() {
    setSaving(true)
    try {
      const { data: fresh } = await api.put('/generate/settings', {
        global_negative: draft.global_negative,
        family_negatives: draft.family_negatives,
        extra_terms: splitTags(draft.extra_terms),
        extra_characters: splitTags(draft.extra_characters),
        extra_negative: draft.extra_negative,
      })
      load(fresh)
      toast.success('Ajustes guardados')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  function setFamily(family, field, value) {
    setDraft((current) => ({
      ...current,
      family_negatives: { ...current.family_negatives, [family]: { ...current.family_negatives[family], [field]: value } },
    }))
  }

  if (!data || !draft) return <div className="p-6 text-sm text-ink-faint">Cargando ajustes…</div>

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4 md:p-6">
      <div className="flex items-center gap-3">
        <h1 className="mr-auto text-xl font-semibold tracking-tight">Ajustes de prompts y política</h1>
        <BaseButton icon={mdiContentSaveOutline} loading={saving} onClick={save}>
          Guardar
        </BaseButton>
      </div>

      <CardBox className="space-y-3 !p-4">
        <h2 className="text-sm font-semibold">Negativo global</h2>
        <p className="text-xs text-ink-faint">Se añade al negativo de todas las generaciones, de cualquier modelo.</p>
        <textarea
          rows={2}
          className={FIELD}
          placeholder="ej. text, watermark, signature"
          value={draft.global_negative}
          onChange={(event) => setDraft({ ...draft, global_negative: event.target.value })}
        />
      </CardBox>

      <CardBox className="space-y-3 !p-4">
        <h2 className="text-sm font-semibold">Negativos por familia de modelo</h2>
        <p className="text-xs text-ink-faint">Vacío = se usa el default (mostrado como sugerencia). "Seguro" se aplica solo con el modo adulto apagado.</p>
        {data.families.map((family) => (
          <details key={family.family} className="rounded-lg border border-line p-3">
            <summary className="cursor-pointer text-xs font-medium">
              {family.label}
              {draft.family_negatives[family.family]?.negative || draft.family_negatives[family.family]?.safe_negative ? (
                <span className="ml-2 text-brand-600 dark:text-brand-400">personalizado</span>
              ) : null}
            </summary>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {[
                ['negative', 'Negativo de calidad', family.default_negative],
                ['safe_negative', 'Negativo modo seguro', family.default_safe_negative],
              ].map(([field, label, fallback]) => (
                <div key={field}>
                  <div className="mb-1 flex items-center justify-between">
                    <span className={LABEL}>{label}</span>
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 text-[11px] text-ink-faint hover:text-ink"
                      onClick={() => setFamily(family.family, field, '')}
                    >
                      <svg viewBox="0 0 24 24" className="size-3" aria-hidden="true">
                        <path d={mdiRestore} fill="currentColor" />
                      </svg>
                      Default
                    </button>
                  </div>
                  <textarea
                    rows={3}
                    className={FIELD}
                    placeholder={fallback}
                    value={draft.family_negatives[family.family]?.[field] ?? ''}
                    onChange={(event) => setFamily(family.family, field, event.target.value)}
                  />
                </div>
              ))}
            </div>
          </details>
        ))}
      </CardBox>

      <CardBox className="space-y-3 !p-4">
        <h2 className="text-sm font-semibold">Política de contenido</h2>
        <p className="text-xs text-ink-faint">
          Las listas base no se pueden reducir desde aquí. Lo que agregues se suma: términos y personajes bloqueados en modo
          adulto, y negativo obligatorio en todas las generaciones.
        </p>
        <div className="grid gap-2 md:grid-cols-2">
          <ReadOnlyList title="Términos bloqueados (base)" items={data.policy.base_terms} />
          <ReadOnlyList title="Personajes bloqueados (base)" items={data.policy.base_characters} />
          <ReadOnlyList title="Aprendidos de AniList (menores según su edad canónica)" items={data.policy.learned_characters} />
          <div className="rounded-lg border border-line p-2">
            <p className="text-xs font-medium text-ink-soft">Negativo obligatorio (base)</p>
            <p className="mt-1 text-[11px] text-ink-faint">{data.policy.base_negative}</p>
          </div>
        </div>
        <div>
          <label htmlFor="extra_terms" className={LABEL}>
            Términos bloqueados adicionales (separados por coma)
          </label>
          <textarea id="extra_terms" rows={2} className={FIELD} value={draft.extra_terms} onChange={(event) => setDraft({ ...draft, extra_terms: event.target.value })} />
        </div>
        <div>
          <label htmlFor="extra_characters" className={LABEL}>
            Personajes bloqueados adicionales en modo adulto (separados por coma)
          </label>
          <textarea
            id="extra_characters"
            rows={2}
            className={FIELD}
            value={draft.extra_characters}
            onChange={(event) => setDraft({ ...draft, extra_characters: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor="extra_negative" className={LABEL}>
            Negativo obligatorio adicional
          </label>
          <textarea
            id="extra_negative"
            rows={2}
            className={FIELD}
            value={draft.extra_negative}
            onChange={(event) => setDraft({ ...draft, extra_negative: event.target.value })}
          />
        </div>
      </CardBox>
    </div>
  )
}
