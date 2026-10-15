import {
  mdiDeleteOutline,
  mdiDownload,
  mdiHeart,
  mdiHeartOutline,
  mdiImageMultipleOutline,
  mdiRepeat,
} from '@mdi/js'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import BaseButton from '@/components/BaseButton.jsx'
import BaseIcon from '@/components/BaseIcon.jsx'
import BaseModal from '@/components/BaseModal.jsx'
import CardBox from '@/components/CardBox.jsx'
import EmptyState from '@/components/EmptyState.jsx'
import { toast } from '@/hooks/useToast.js'
import api from '@/services/api.js'
import { useImageForm } from '@/stores/imageForm.store.js'
import { useJobsStore } from '@/stores/jobs.store.js'

const PAGE = 60
const FIELD =
  'rounded-lg border border-line bg-panel px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:outline-none'

function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

function Meta({ label, value }) {
  if (value === null || value === undefined || value === '') return null
  return (
    <div className="flex gap-2 text-xs">
      <dt className="w-20 shrink-0 text-ink-faint">{label}</dt>
      <dd className="min-w-0 break-words text-ink">{value}</dd>
    </div>
  )
}

export default function GalleryView() {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [query, setQuery] = useState('')
  const [favorites, setFavorites] = useState(false)
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const debouncedQuery = useDebounced(query)
  const reuse = useImageForm((state) => state.reuse)
  const onJob = useJobsStore((state) => state.onJob)
  const navigate = useNavigate()

  const load = useCallback(
    async (offset = 0) => {
      setLoading(true)
      try {
        const { data } = await api.get('/gallery', {
          params: { q: debouncedQuery || undefined, favorite: favorites || undefined, limit: PAGE, offset },
        })
        setItems((previous) => (offset === 0 ? data.items : [...previous, ...data.items]))
        setTotal(data.total)
      } catch (err) {
        toast.error(err.message)
      } finally {
        setLoading(false)
      }
    },
    [debouncedQuery, favorites],
  )

  useEffect(() => {
    load(0)
  }, [load])

  // New results land at the top as soon as a job finishes.
  useEffect(() => onJob((job) => job.status === 'done' && load(0)), [onJob, load])

  async function toggleFavorite(item) {
    try {
      const { data } = await api.patch(`/gallery/${item.id}`, { favorite: !item.favorite })
      setItems((previous) => previous.map((entry) => (entry.id === data.id ? data : entry)))
      setSelected((current) => (current?.id === data.id ? data : current))
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function remove(item) {
    if (!window.confirm('¿Borrar esta imagen y su archivo? No se puede deshacer.')) return
    try {
      await api.delete(`/gallery/${item.id}`)
      setItems((previous) => previous.filter((entry) => entry.id !== item.id))
      setTotal((value) => value - 1)
      setSelected(null)
      toast.success('Borrada')
    } catch (err) {
      toast.error(err.message)
    }
  }

  function reuseItem(item) {
    reuse(item.params ?? {})
    navigate('/')
  }

  return (
    <div className="p-4 md:p-6">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-xl font-semibold tracking-tight">
          Galería <span className="text-sm font-normal text-ink-faint">· {total}</span>
        </h1>
        <input
          type="search"
          aria-label="Buscar en la galería"
          placeholder="Buscar por prompt o modelo…"
          className={`${FIELD} w-64`}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <BaseButton
          variant={favorites ? 'primary' : 'outline'}
          icon={favorites ? mdiHeart : mdiHeartOutline}
          onClick={() => setFavorites((value) => !value)}
        >
          Favoritos
        </BaseButton>
      </div>

      {items.length === 0 && !loading ? (
        <CardBox>
          <EmptyState
            icon={mdiImageMultipleOutline}
            title={query || favorites ? 'Nada coincide con el filtro' : 'La galería está vacía'}
            description={
              query || favorites
                ? 'Prueba con otra búsqueda o quita el filtro de favoritos.'
                : 'Lo que generes aparecerá aquí con el prompt y los parámetros que lo produjeron.'
            }
          />
        </CardBox>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setSelected(item)}
              aria-label={`Abrir #${item.id}: ${(item.params?.user_prompt ?? item.prompt).slice(0, 80)}`}
              className="group relative overflow-hidden rounded-xl border border-line bg-panel text-left"
            >
              {item.kind === 'video' ? (
                <video src={item.url} muted loop playsInline className="aspect-[2/3] w-full object-cover" />
              ) : (
                <img
                  src={item.thumb_url ?? item.url}
                  alt={item.prompt}
                  loading="lazy"
                  className="aspect-[2/3] w-full object-cover transition-transform duration-200 group-hover:scale-[1.02]"
                />
              )}
              {item.favorite ? (
                <BaseIcon path={mdiHeart} size="sm" className="absolute top-2 right-2 text-brand-500 drop-shadow" />
              ) : null}
            </button>
          ))}
        </div>
      )}

      {items.length < total ? (
        <div className="mt-6 flex justify-center">
          <BaseButton variant="outline" loading={loading} onClick={() => load(items.length)}>
            Cargar más
          </BaseButton>
        </div>
      ) : null}

      <BaseModal
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected ? `#${selected.id} · ${selected.width ?? '?'}×${selected.height ?? '?'}` : ''}
        size="lg"
        footer={
          selected ? (
            <>
              <BaseButton variant="danger" icon={mdiDeleteOutline} onClick={() => remove(selected)}>
                Borrar
              </BaseButton>
              <a
                href={selected.url}
                download
                className="inline-flex h-10 items-center gap-2 rounded-md border border-line px-4 text-sm font-medium text-ink hover:bg-elevated"
              >
                <BaseIcon path={mdiDownload} size="sm" /> Descargar
              </a>
              <BaseButton
                variant="outline"
                icon={selected.favorite ? mdiHeart : mdiHeartOutline}
                onClick={() => toggleFavorite(selected)}
              >
                {selected.favorite ? 'Quitar favorito' : 'Favorito'}
              </BaseButton>
              {selected.params?.mode ? (
                <BaseButton icon={mdiRepeat} onClick={() => reuseItem(selected)}>
                  Reusar
                </BaseButton>
              ) : null}
            </>
          ) : null
        }
      >
        {selected ? (
          <div className="grid gap-4 md:grid-cols-[1fr_16rem]">
            {selected.kind === 'video' ? (
              <video src={selected.url} controls className="max-h-[70vh] w-full rounded-lg bg-black" />
            ) : (
              <img src={selected.url} alt={selected.prompt} className="max-h-[70vh] w-full rounded-lg object-contain" />
            )}
            <dl className="space-y-2">
              <Meta label="Modelo" value={selected.model?.split(':').slice(1).join(':')} />
              <Meta label="Semilla" value={selected.seed} />
              <Meta label="Pasos" value={selected.params?.steps} />
              <Meta label="CFG" value={selected.params?.cfg} />
              <Meta label="Sampler" value={selected.params?.sampler && `${selected.params.sampler} / ${selected.params.scheduler}`} />
              <Meta label="Adulto" value={selected.adult ? 'sí' : null} />
              <Meta label="Prompt" value={selected.prompt} />
              <Meta label="Negativo" value={selected.negative} />
            </dl>
          </div>
        ) : null}
      </BaseModal>
    </div>
  )
}
