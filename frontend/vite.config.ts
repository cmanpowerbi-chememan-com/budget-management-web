import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Local dev only — A7 backend has no `/api` prefix (see backend/app/main.py:
// routers are mounted directly as /health /me /scope /budget /approval/*),
// so the proxy forwards each known route namespace as-is rather than
// rewriting an /api/* prefix that doesn't exist server-side.
const BACKEND_DEV_SERVER = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/health': BACKEND_DEV_SERVER,
      '/me': BACKEND_DEV_SERVER,
      '/scope': BACKEND_DEV_SERVER,
      '/budget': BACKEND_DEV_SERVER,
      '/approval': BACKEND_DEV_SERVER,
      '/attachments': BACKEND_DEV_SERVER,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // Playwright's permanent E2E suite lives in ./e2e (frontend/e2e/*.spec.ts)
    // and must never be picked up by Vitest's default *.spec.ts include glob.
    exclude: ['e2e/**', 'node_modules/**'],
  },
})
