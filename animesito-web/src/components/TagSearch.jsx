import { useEffect, useState } from 'react'

import useDebounced from '@/hooks/useDebounced.js'
import api from '@/services/api.js'

const FIELD =
  'w-full rounded-lg border border-line bg-panel px-3 py-1.5 text-xs text-ink placeholder:text-ink-faint focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:outline-none'

function formatCount(count) {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`
  if (count >= 1_000) return `${Math.round(count / 1_000)}k`
  return String(count)
}

// Danbooru autocomplete: the post count tells how well the model knows a tag.
export default function TagSearch({ onPick, category = 'general', placeholder = 'Buscar tag en Danbooru…', label }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const debounced = useDebounced(query.trim(), 350)

  useEffect(() => {
    if (debounced.length < 2) {
      setResults([])
      return undefined
    }
    let alive = true
    api
      .get('/prompts/tags', { params: { q: debounced, category } })
      .then(({ data }) => alive && setResults(data))
      .catch(() => alive && setResults([]))
    return () => {
      alive = false
    }
  }, [debounced, category])

  function pick(tag) {
    onPick(tag)
    setQuery('')
    setResults([])
  }

  return (
    <div className="relative">
      <input
        type="search"
        aria-label={label ?? placeholder}
        placeholder={placeholder}
        className={FIELD}
        value={query}
        onChange={(event) => {
          setQuery(event.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
            if (results[0]) pick(results[0].label)
            else if (query.trim()) pick(query.trim())
          }
        }}
      />
      {open && results.length > 0 ? (
        <ul className="absolute z-30 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-line bg-panel shadow-lg">
          {results.map((tag) => (
            <li key={tag.tag}>
              <button
                type="button"
                className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-xs hover:bg-elevated"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => pick(tag.label)}
              >
                <span className="truncate">{tag.label}</span>
                <span className="shrink-0 text-ink-faint">{formatCount(tag.count)}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

export { formatCount }
