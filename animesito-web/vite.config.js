import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The backend, as Caddy exposes it in production: /api/* with the prefix
// stripped, and /storage/* for gallery files. Proxying the same two paths in
// development keeps the app single-origin everywhere (no CORS, SSE included).
const API = process.env.ANIMESITO_API ?? 'http://127.0.0.1:7789'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 7799,
    proxy: {
      '/api': { target: API, rewrite: (path) => path.replace(/^\/api/, '') },
      '/storage': { target: API },
    },
  },
})
