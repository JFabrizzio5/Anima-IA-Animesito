import { useEffect, useState } from 'react'

import { formatCount } from '@/components/TagSearch.jsx'
import useDebounced from '@/hooks/useDebounced.js'
import api from '@/services/api.js'

const FIELD =
  'w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:outline-none'

const SOURCE = {
  both: { text: 'Danbooru + AniList', tone: 'text-emerald-600 dark:text-emerald-400' },
  danbooru: { text: 'Danbooru', tone: 'text-ink-faint' },
  anilist: { text: 'Solo AniList: el modelo puede no conocerlo', tone: 'text-amber-600 dark:text-amber-400' },
}

// v1's AniList lookup, now merged with Danbooru: the tag the model knows, the
// picture and series from AniList, and the canonical age.
export default function CharacterSearch({ onPick }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const debounced = useDebounced(query.trim(), 400)

  useEffect(() => {
    if (debounced.length < 2) {
      setResults([])
      setError('')
      return undefined
    }
    let alive = true
    setLoading(true)
    api
      .get('/prompts/characters', { params: { q: debounced } })
      .then(({ data }) => {
        if (!alive) return
        setResults(data)
        setError(data.length ? '' : 'Sin resultados')
      })
      .catch((err) => alive && setError(err.message))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [debounced])

  return (
    <div>
      <input
        type="search"
        aria-label="Buscar personaje"
        placeholder="Buscar personaje (ej. tifa, yor, marin kitagawa)…"
        className={FIELD}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      {loading ? <p className="mt-2 text-xs text-ink-faint">Buscando en Danbooru y AniList…</p> : null}
      {error && !loading ? <p className="mt-2 text-xs text-ink-faint">{error}</p> : null}
      {results.length > 0 ? (
        <ul className="mt-2 grid max-h-72 gap-1.5 overflow-y-auto sm:grid-cols-2">
          {results.map((hit) => (
            <li key={hit.tag}>
              <button
                type="button"
                onClick={() => {
                  onPick(hit)
                  setQuery('')
                  setResults([])
                }}
                className="flex w-full items-center gap-2 rounded-lg border border-line p-1.5 text-left hover:bg-elevated"
              >
                {hit.image ? (
                  <img src={hit.image} alt="" loading="lazy" className="size-10 shrink-0 rounded-md object-cover" />
                ) : (
                  <span className="size-10 shrink-0 rounded-md bg-elevated" aria-hidden="true" />
                )}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-medium text-ink">{hit.label}</span>
                  <span className="block truncate text-[11px] text-ink-faint">
                    {hit.series ?? hit.tag}
                    {hit.count ? ` · ${formatCount(hit.count)} posts` : ''}
                  </span>
                  <span className={`block truncate text-[10px] ${SOURCE[hit.source]?.tone ?? ''}`}>
                    {SOURCE[hit.source]?.text}
                    {hit.minor ? ' · menor (canon): sin modo adulto' : ''}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
