import { mdiClose, mdiDiceMultipleOutline } from '@mdi/js'
import { useEffect, useState } from 'react'

import BaseButton from '@/components/BaseButton.jsx'
import BaseIcon from '@/components/BaseIcon.jsx'
import CharacterSearch from '@/components/CharacterSearch.jsx'
import TagSearch from '@/components/TagSearch.jsx'
import { toast } from '@/hooks/useToast.js'
import api from '@/services/api.js'
import { CHARACTER_ZONES, MAX_CHARACTERS, SCENE_ZONES, SUBJECTS, autoSubject, useBuilder } from '@/stores/builder.store.js'

const SELECT =
  'w-full rounded-lg border border-line bg-panel px-2 py-1.5 text-xs text-ink focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:outline-none'
const LABEL = 'mb-1 block text-xs font-medium text-ink-soft'

function Chip({ children, onRemove, active = true, onClick, title }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${
        active
          ? 'border-brand-300 bg-brand-50 text-brand-700 dark:border-brand-800 dark:bg-brand-900/30 dark:text-brand-200'
          : 'border-line text-ink-faint line-through'
      }`}
    >
      {onClick ? (
        <button type="button" onClick={onClick} className="max-w-48 truncate">
          {children}
        </button>
      ) : (
        <span className="max-w-48 truncate">{children}</span>
      )}
      {onRemove ? (
        <button type="button" aria-label={`Quitar ${children}`} onClick={onRemove} className="opacity-70 hover:opacity-100">
          <BaseIcon path={mdiClose} size="sm" className="!size-3" />
        </button>
      ) : null}
    </span>
  )
}

function ZoneEditor({ zone, tags, onAdd, onRemove, compact = false }) {
  return (
    <div>
      <p className={LABEL}>{zone.label}</p>
      <div className={compact ? 'grid grid-cols-2 gap-1' : 'space-y-1'}>
        <select
          aria-label={`Preset de ${zone.label}`}
          className={SELECT}
          value=""
          onChange={(event) => event.target.value && onAdd(event.target.value)}
        >
          <option value="">Preset…</option>
          {zone.options.map((option) => (
            <option key={option.label} value={option.tags}>
              {option.label}
            </option>
          ))}
        </select>
        <TagSearch label={`Buscar tag para ${zone.label}`} placeholder="Buscar tag…" onPick={onAdd} />
      </div>
      {tags.length ? (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {tags.map((tag) => (
            <Chip key={tag} onRemove={() => onRemove(tag)}>
              {tag}
            </Chip>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function CharacterCard({ character, zones, index, total }) {
  const builder = useBuilder()
  return (
    <div className="rounded-lg border border-line p-2.5">
      <div className="flex items-center gap-2">
        {character.image ? <img src={character.image} alt="" className="size-9 rounded object-cover" /> : null}
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium">
            {total > 1 ? <span className="mr-1 text-ink-faint">#{index + 1}</span> : null}
            {character.label}
          </p>
          <p className="truncate text-[11px] text-ink-faint">
            {character.tag}
            {character.seriesTag ? ` · ${character.seriesTag.replace(/_/g, ' ')}` : ''}
          </p>
        </div>
        <button
          type="button"
          aria-label={`Quitar ${character.label}`}
          className="rounded p-1 text-ink-faint hover:bg-elevated hover:text-ink"
          onClick={() => builder.removeCharacter(character.tag)}
        >
          <BaseIcon path={mdiClose} size="sm" />
        </button>
      </div>

      {character.traits?.length ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {character.traits.map((trait) => (
            <Chip key={trait.tag} active={trait.on} title="Clic para activar/desactivar" onClick={() => builder.toggle(character.tag, 'traits', trait.tag)}>
              {trait.tag.replace(/_/g, ' ')}
            </Chip>
          ))}
        </div>
      ) : null}
      {character.outfit?.length ? (
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          <span className="text-[10px] text-ink-faint">Ropa canónica:</span>
          {character.outfit.map((piece) => (
            <Chip key={piece.tag} active={piece.on} title="Clic para usar su ropa de siempre" onClick={() => builder.toggle(character.tag, 'outfit', piece.tag)}>
              {piece.tag.replace(/_/g, ' ')}
            </Chip>
          ))}
        </div>
      ) : null}

      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        {zones.map((zone) => (
          <ZoneEditor
            key={zone.id}
            zone={zone}
            tags={character.zones?.[zone.id] ?? []}
            onAdd={(text) => builder.addCharacterTags(character.tag, zone.id, text)}
            onRemove={(tag) => builder.removeCharacterTag(character.tag, zone.id, tag)}
          />
        ))}
      </div>
    </div>
  )
}

// v1's "Constructor Modular", one card per character: each with its own
// traits, canon outfit, outfit/pose/expression; the scene is shared. While
// "Incluir al generar" is on, it goes into the generation by itself.
export default function PromptBuilder({ adult }) {
  const [catalog, setCatalog] = useState([])
  const builder = useBuilder()

  useEffect(() => {
    api
      .get('/prompts/builder')
      .then(({ data }) => setCatalog(data.zones))
      .catch((err) => toast.error(err.message))
  }, [])

  // Characters saved before canon outfits existed get them on first render.
  useEffect(() => {
    for (const character of useBuilder.getState().characters) {
      if (character.outfit?.length || !character.traits) continue
      api
        .get(`/prompts/characters/${encodeURIComponent(character.tag)}/traits`)
        .then(({ data }) =>
          useBuilder.getState().setTraits(character.tag, { traits: data.traits, outfit: data.outfit, seriesTag: data.series[0]?.tag }),
        )
        .catch(() => {})
    }
  }, [])

  async function addCharacter(hit) {
    if (builder.characters.length >= MAX_CHARACTERS) {
      toast.error(`Máximo ${MAX_CHARACTERS} personajes por imagen`)
      return
    }
    builder.addCharacter(hit)
    try {
      const { data } = await api.get(`/prompts/characters/${encodeURIComponent(hit.tag)}/traits`)
      builder.setTraits(hit.tag, { traits: data.traits, outfit: data.outfit, seriesTag: data.series[0]?.tag })
    } catch (err) {
      toast.error(`Rasgos de ${hit.label}: ${err.message}`)
    }
  }

  const characterZones = catalog.filter((zone) => CHARACTER_ZONES.includes(zone.id))
  const sceneZones = catalog.filter((zone) => SCENE_ZONES.includes(zone.id))

  function randomize() {
    for (const zone of sceneZones) {
      if (!zone.options.length) continue
      builder.addSceneTags(zone.id, zone.options[Math.floor(Math.random() * zone.options.length)].tags)
    }
    for (const character of builder.characters) {
      for (const zone of characterZones) {
        if (!zone.options.length) continue
        builder.addCharacterTags(character.tag, zone.id, zone.options[Math.floor(Math.random() * zone.options.length)].tags)
      }
    }
  }

  const composed = builder.compose()
  const minors = builder.characters.filter((item) => item.minor)

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-[9rem_1fr]">
        <div>
          <label htmlFor="subject" className={LABEL}>
            Sujeto
          </label>
          <select id="subject" className={SELECT} value={builder.subject} onChange={(event) => builder.setSubject(event.target.value)}>
            {SUBJECTS.map((subject) => (
              <option key={subject || 'none'} value={subject}>
                {subject === 'auto' ? `Auto (${autoSubject(builder.characters)})` : subject || '(ninguno)'}
              </option>
            ))}
          </select>
        </div>
        <div>
          <p className={LABEL}>
            Personajes <span className="font-normal text-ink-faint">({builder.characters.length}/{MAX_CHARACTERS})</span>
          </p>
          <CharacterSearch onPick={addCharacter} />
        </div>
      </div>

      {builder.characters.length > 0 ? (
        <div className="space-y-2">
          {builder.characters.map((character, index) => (
            <CharacterCard key={character.tag} character={character} zones={characterZones} index={index} total={builder.characters.length} />
          ))}
          {builder.characters.length > 1 ? (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-ink-soft">Separación:</span>
              {[
                ['blend', 'Prompts separados (BREAK)'],
                ['columns', 'Columnas izquierda → derecha'],
              ].map(([value, text]) => (
                <label key={value} className="flex items-center gap-1">
                  <input type="radio" name="layout" className="accent-brand-600" checked={builder.layout === value} onChange={() => builder.setLayout(value)} />
                  {text}
                </label>
              ))}
            </div>
          ) : null}
          {adult && minors.length ? (
            <p className="text-xs text-brand-600 dark:text-brand-400">
              {minors.map((item) => item.label).join(', ')}: menor según su canon. El modo adulto será rechazado.
            </p>
          ) : null}
        </div>
      ) : null}

      <div>
        <p className="mb-2 text-xs font-medium text-ink-soft">Escena (compartida)</p>
        <div className="grid gap-3 sm:grid-cols-2">
          {sceneZones.map((zone) => (
            <ZoneEditor
              key={zone.id}
              zone={zone}
              tags={builder.scene[zone.id] ?? []}
              onAdd={(text) => builder.addSceneTags(zone.id, text)}
              onRemove={(tag) => builder.removeSceneTag(zone.id, tag)}
            />
          ))}
        </div>
      </div>

      <div className="space-y-1 rounded-lg bg-elevated p-2 text-xs break-words text-ink-soft">
        <p>{composed.scene || 'Vacío'}</p>
        {composed.characters.map((text, index) => (
          <p key={index}>
            <span className="text-ink-faint">#{index + 1}:</span> {text}
          </p>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="mr-auto flex items-center gap-2 text-xs font-medium">
          <input type="checkbox" className="accent-brand-600" checked={builder.enabled} onChange={(event) => builder.setEnabled(event.target.checked)} />
          Incluir al generar <span className="font-normal text-ink-faint">(va antes de tu prompt)</span>
        </label>
        <BaseButton size="sm" variant="outline" icon={mdiDiceMultipleOutline} onClick={randomize}>
          Aleatorio
        </BaseButton>
        <BaseButton size="sm" variant="ghost" onClick={builder.clear}>
          Limpiar
        </BaseButton>
      </div>
    </div>
  )
}
