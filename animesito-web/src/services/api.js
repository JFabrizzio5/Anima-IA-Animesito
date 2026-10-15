import axios from 'axios'

// Same origin in development (Vite proxies /api and /storage to the backend)
// and in production (Caddy does), so there is no CORS and no per-environment
// rebuild. The timeout covers the slowest call: an LLM prompt enhancement.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: Number(import.meta.env.VITE_API_TIMEOUT) || 60000,
})

// The backend refuses state-changing requests without this header (CSRF guard
// for a login-less app on localhost). A cross-origin page cannot add it
// without a preflight, which the backend's CORS allow-list refuses.
api.interceptors.request.use((config) => {
  config.headers['X-Animesito'] = '1'
  return config
})

// The backend speaks RFC 7807; surface `detail` instead of axios's generic text.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const problem = error.response?.data
    if (problem?.detail) {
      error.message = Array.isArray(problem.detail)
        ? problem.detail.map((item) => item.msg ?? String(item)).join('; ')
        : problem.detail
    } else if (problem?.title) {
      error.message = problem.title
    }
    return Promise.reject(error)
  },
)

export function apiUrl(path) {
  const base = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')
  return `${base}${path}`
}

export default api
