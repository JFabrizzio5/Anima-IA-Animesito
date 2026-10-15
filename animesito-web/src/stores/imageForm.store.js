import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const DEFAULT_FORM = {
  model: '',
  prompt: '',
  negative: '',
  width: 832,
  height: 1216,
  steps: null,
  cfg: null,
  sampler: null,
  scheduler: null,
  seed: -1,
  count: 1,
  batch_size: 1,
  adult: false,
  quality_tags: true,
  loras: [],
  // v1's default "Anime limpio equilibrado" (styles.toml).
  style: 'clean_anime',
  hires: false,
}

/**
 * The image form, remembered across reloads (per browser, a convenience only:
 * the gallery is the record of what was generated).
 */
export const useImageForm = create(
  persist(
    (set) => ({
      form: DEFAULT_FORM,
      setField: (field, value) => set((state) => ({ form: { ...state.form, [field]: value } })),
      patch: (values) => set((state) => ({ form: { ...state.form, ...values } })),
      reset: () => set({ form: DEFAULT_FORM }),
      /** Load the parameters a gallery item was generated with. */
      reuse: (params) =>
        set((state) => ({
          form: {
            ...state.form,
            model: params.model ?? state.form.model,
            prompt: params.user_prompt ?? params.prompt ?? state.form.prompt,
            negative: params.user_negative ?? '',
            width: params.width ?? state.form.width,
            height: params.height ?? state.form.height,
            steps: params.steps ?? null,
            cfg: params.cfg ?? null,
            sampler: params.sampler ?? null,
            scheduler: params.scheduler ?? null,
            seed: params.seed ?? -1,
            adult: Boolean(params.adult),
            quality_tags: params.quality_tags ?? true,
            loras: (params.loras ?? []).map((lora) => ({ name: lora.name, strength: lora.strength })),
            style: params.style ?? null,
            hires: Boolean(params.hires),
            count: 1,
            batch_size: 1,
          },
        })),
    }),
    {
      name: 'animesito:image-form',
      version: 2,
      migrate: (state) => ({ form: { ...DEFAULT_FORM, ...(state?.form ?? {}) } }),
      partialize: (state) => ({ form: state.form }),
    },
  ),
)
