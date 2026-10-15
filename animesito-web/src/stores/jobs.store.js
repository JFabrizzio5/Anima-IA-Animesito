import { create } from 'zustand'

import api, { apiUrl } from '@/services/api.js'

export const FINISHED = new Set(['done', 'error', 'cancelled'])

const RETRY_MAX_MS = 15000

/**
 * Jobs as the server reports them, kept current by the SSE stream.
 *
 * The stream only carries changes, so a (re)connect first reloads the recent
 * list: anything that changed while the socket was down is picked up there.
 */
export const useJobsStore = create((set, get) => ({
  jobs: {},
  order: [],
  connected: false,
  listeners: new Set(),

  upsert(job) {
    set((state) => {
      const exists = Boolean(state.jobs[job.id])
      return {
        jobs: { ...state.jobs, [job.id]: { ...state.jobs[job.id], ...job } },
        order: exists ? state.order : [job.id, ...state.order],
      }
    })
    get().listeners.forEach((listener) => listener(get().jobs[job.id]))
  },

  /** Called with every job update; returns an unsubscribe function. */
  onJob(listener) {
    get().listeners.add(listener)
    return () => get().listeners.delete(listener)
  },

  async refresh() {
    const { data } = await api.get('/jobs', { params: { limit: 30 } })
    set(() => ({
      jobs: Object.fromEntries(data.map((job) => [job.id, job])),
      order: data.map((job) => job.id),
    }))
  },

  async cancel(id) {
    const { data } = await api.post(`/jobs/${id}/cancel`)
    get().upsert(data)
  },

  dismissFinished() {
    set((state) => {
      const order = state.order.filter((id) => !FINISHED.has(state.jobs[id]?.status))
      return { order, jobs: Object.fromEntries(order.map((id) => [id, state.jobs[id]])) }
    })
  },
}))

let source = null
let retryDelay = 1000

/** Open the event stream once for the whole app; reconnects with backoff. */
export function connectJobEvents() {
  if (source) return
  const open = () => {
    source = new EventSource(apiUrl('/jobs/events'))
    source.onopen = () => {
      retryDelay = 1000
      useJobsStore.setState({ connected: true })
      useJobsStore.getState().refresh().catch(() => {})
    }
    source.addEventListener('job', (message) => {
      try {
        useJobsStore.getState().upsert(JSON.parse(message.data))
      } catch {
        // A malformed frame is dropped; the next refresh corrects the list.
      }
    })
    source.onerror = () => {
      useJobsStore.setState({ connected: false })
      source.close()
      source = null
      setTimeout(open, retryDelay)
      retryDelay = Math.min(retryDelay * 2, RETRY_MAX_MS)
    }
  }
  open()
}
