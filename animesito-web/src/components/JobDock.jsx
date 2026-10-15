import { mdiChevronDown, mdiChevronUp, mdiClose } from '@mdi/js'
import { useState } from 'react'

import BaseButton from '@/components/BaseButton.jsx'
import BaseIcon from '@/components/BaseIcon.jsx'
import { toast } from '@/hooks/useToast.js'
import { FINISHED, useJobsStore } from '@/stores/jobs.store.js'

const LABELS = {
  queued: 'En cola',
  submitted: 'Enviado',
  running: 'Generando',
  ingesting: 'Guardando',
  done: 'Listo',
  error: 'Error',
  cancelled: 'Cancelado',
}

const BAR = {
  done: 'bg-emerald-500',
  error: 'bg-brand-500',
  cancelled: 'bg-ink-faint',
}

// The GPU queue, always in view: what is running, what waits, what failed and
// why. Collapsible because a long session accumulates finished entries.
export default function JobDock() {
  const jobs = useJobsStore((state) => state.jobs)
  const order = useJobsStore((state) => state.order)
  const connected = useJobsStore((state) => state.connected)
  const cancel = useJobsStore((state) => state.cancel)
  const dismissFinished = useJobsStore((state) => state.dismissFinished)
  const [open, setOpen] = useState(true)

  const visible = order.map((id) => jobs[id]).filter(Boolean).slice(0, 12)
  const active = visible.filter((job) => !FINISHED.has(job.status)).length
  if (visible.length === 0) return null

  return (
    <section
      aria-label="Cola de trabajos"
      className="fixed right-4 bottom-4 z-40 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-line bg-panel shadow-lg"
    >
      <header className="flex items-center gap-2 border-b border-line px-3 py-2">
        <span
          className={`size-2 rounded-full ${connected ? 'bg-emerald-500' : 'bg-amber-500'}`}
          title={connected ? 'Conectado' : 'Reconectando…'}
          aria-hidden="true"
        />
        <h2 className="flex-1 text-sm font-medium">
          Cola GPU {active ? <span className="text-ink-faint">· {active} activos</span> : null}
        </h2>
        <BaseButton variant="ghost" size="sm" onClick={dismissFinished}>
          Limpiar
        </BaseButton>
        <BaseButton
          variant="ghost"
          size="sm"
          icon={open ? mdiChevronDown : mdiChevronUp}
          aria-label={open ? 'Contraer cola' : 'Expandir cola'}
          onClick={() => setOpen((value) => !value)}
        />
      </header>
      {open ? (
        <ul className="max-h-80 divide-y divide-line overflow-y-auto">
          {visible.map((job) => (
            <li key={job.id} className="px-3 py-2">
              <div className="flex items-center gap-2">
                <p className="min-w-0 flex-1 truncate text-xs text-ink" title={job.title}>
                  {job.title}
                </p>
                <span className="text-xs text-ink-faint">{LABELS[job.status] ?? job.status}</span>
                {!FINISHED.has(job.status) && job.status !== 'ingesting' ? (
                  <button
                    type="button"
                    className="rounded p-0.5 text-ink-faint hover:bg-elevated hover:text-ink"
                    aria-label={`Cancelar ${job.title}`}
                    onClick={() => cancel(job.id).catch((err) => toast.error(err.message))}
                  >
                    <BaseIcon path={mdiClose} size="sm" />
                  </button>
                ) : null}
              </div>
              <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-elevated">
                <div
                  className={`h-full rounded-full transition-[width] duration-300 ${BAR[job.status] ?? 'bg-brand-500'}`}
                  style={{ width: `${Math.round((job.status === 'done' ? 1 : job.progress) * 100)}%` }}
                />
              </div>
              {job.status === 'error' && job.error ? (
                <p className="mt-1 text-xs break-words text-brand-600 dark:text-brand-400">{job.error}</p>
              ) : (
                <p className="mt-1 text-xs text-ink-faint">{job.progress_text}</p>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
