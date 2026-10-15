import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const SUBJECTS = ['auto', '1girl', '1boy', '2girls', '2boys', '1girl, 1boy', '3girls', 'solo', '']

// Zones that belong to one character, and zones that describe the whole scene.
// Ids match modules/prompts/builder.toml.
export const CHARACTER_ZONES = ['outfit', 'pose', 'expression']
export const SCENE_ZONES = ['environment', 'extra']

export const MAX_CHARACTERS = 4

// ComfyUI reads "(word)" as emphasis; a Danbooru tag such as
// "tsunade (naruto)" must reach it escaped or the qualifier becomes a weight.
export function escapeTag(tag) {
  return tag.replace(/_/g, ' ').replace(/([()])/g, '\\$1')
}

export function splitTags(text) {
  return text
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
}

function addUnique(list, text) {
  const next = [...(list ?? [])]
  for (const tag of splitTags(text)) if (!next.includes(tag)) next.push(tag)
  return next
}

function toggleIn(list, tag) {
  return (list ?? []).map((item) => (item.tag === tag ? { ...item, on: !item.on } : item))
}

/** "1girl", "2girls", "1girl, 1boy"... from the characters' genders. */
export function autoSubject(characters) {
  if (!characters.length) return '1girl'
  const girls = characters.filter((item) => item.gender !== 'Male').length
  const boys = characters.length - girls
  const part = (count, word) => (count ? `${count}${word}${count > 1 ? 's' : ''}` : null)
  return [part(girls, 'girl'), part(boys, 'boy')].filter(Boolean).join(', ')
}

function characterTags(character) {
  const parts = [escapeTag(character.tag)]
  if (character.seriesTag) parts.push(escapeTag(character.seriesTag))
  for (const trait of character.traits ?? []) if (trait.on) parts.push(escapeTag(trait.tag))
  for (const piece of character.outfit ?? []) if (piece.on) parts.push(escapeTag(piece.tag))
  for (const zone of CHARACTER_ZONES) for (const tag of character.zones?.[zone] ?? []) parts.push(escapeTag(tag))
  return [...new Set(parts)].join(', ')
}

/**
 * The modular builder (v1's "Constructor Modular"), one card per character.
 * While `enabled`, generation sends the scene in front of the typed prompt and,
 * with two or more characters, each character as its own prompt so their
 * traits stay apart (the backend encodes them separately).
 */
export const useBuilder = create(
  persist(
    (set, get) => ({
      enabled: true,
      subject: 'auto',
      layout: 'blend', // blend | columns
      characters: [], // { tag, label, gender, seriesTag, minor, image, traits, outfit, zones }
      scene: {}, // zoneId -> [tag]

      setEnabled: (enabled) => set({ enabled }),
      setSubject: (subject) => set({ subject }),
      setLayout: (layout) => set({ layout }),

      addCharacter: (hit) =>
        set((state) =>
          state.characters.length >= MAX_CHARACTERS || state.characters.some((item) => item.tag === hit.tag)
            ? state
            : {
                characters: [
                  ...state.characters,
                  {
                    tag: hit.tag,
                    label: hit.label,
                    gender: hit.gender ?? null,
                    seriesTag: hit.series_tag ?? null,
                    minor: hit.minor,
                    image: hit.image,
                    traits: [],
                    outfit: [],
                    zones: {},
                  },
                ],
              },
        ),

      setTraits: (tag, { traits, outfit, seriesTag }) =>
        set((state) => ({
          characters: state.characters.map((item) =>
            item.tag === tag
              ? {
                  ...item,
                  seriesTag: item.seriesTag ?? seriesTag ?? null,
                  // The most frequent traits start on: they make the character
                  // recognisable. The canon outfit starts off.
                  traits: traits.map((trait) => ({ tag: trait.tag, on: trait.frequency >= 0.5 })),
                  outfit: (outfit ?? []).map((piece) => ({ tag: piece.tag, on: false })),
                }
              : item,
          ),
        })),

      toggle: (tag, kind, itemTag) =>
        set((state) => ({
          characters: state.characters.map((item) =>
            item.tag === tag ? { ...item, [kind]: toggleIn(item[kind], itemTag) } : item,
          ),
        })),

      addCharacterTags: (tag, zone, text) =>
        set((state) => ({
          characters: state.characters.map((item) =>
            item.tag === tag ? { ...item, zones: { ...item.zones, [zone]: addUnique(item.zones?.[zone], text) } } : item,
          ),
        })),

      removeCharacterTag: (tag, zone, value) =>
        set((state) => ({
          characters: state.characters.map((item) =>
            item.tag === tag
              ? { ...item, zones: { ...item.zones, [zone]: (item.zones?.[zone] ?? []).filter((entry) => entry !== value) } }
              : item,
          ),
        })),

      removeCharacter: (tag) => set((state) => ({ characters: state.characters.filter((item) => item.tag !== tag) })),

      addSceneTags: (zone, text) => set((state) => ({ scene: { ...state.scene, [zone]: addUnique(state.scene[zone], text) } })),

      removeSceneTag: (zone, value) =>
        set((state) => ({ scene: { ...state.scene, [zone]: (state.scene[zone] ?? []).filter((entry) => entry !== value) } })),

      clear: () => set({ characters: [], scene: {} }),

      /**
       * { scene, characters }: with one character everything goes in `scene`
       * (nothing to keep apart); with two or more, each character is its own
       * prompt and `scene` carries the subject count and the shared zones.
       */
      compose: () => {
        const { subject, characters, scene } = get()
        const sceneTags = SCENE_ZONES.flatMap((zone) => (scene[zone] ?? []).map(escapeTag))
        const hasAnything = characters.length || sceneTags.length
        const subjectText = subject === 'auto' ? autoSubject(characters) : subject
        const head = hasAnything && subjectText ? [subjectText] : []
        if (characters.length <= 1) {
          const parts = [...head, ...(characters[0] ? splitTags(characterTags(characters[0])) : []), ...sceneTags]
          return { scene: [...new Set(parts)].join(', '), characters: [] }
        }
        return {
          scene: [...new Set([...head, ...sceneTags])].join(', '),
          characters: characters.map(characterTags),
        }
      },
    }),
    {
      name: 'animesito:builder',
      version: 3,
      migrate: (state) => ({
        enabled: true,
        subject: 'auto',
        layout: 'blend',
        characters: (state?.characters ?? []).map((item) => ({ zones: {}, gender: null, ...item })),
        scene: {},
      }),
    },
  ),
)

/** Builder scene first, then whatever the user typed; duplicates dropped. */
export function finalPrompt(builderText, typed) {
  return [...new Set([...splitTags(builderText), ...splitTags(typed)])].join(', ')
}
