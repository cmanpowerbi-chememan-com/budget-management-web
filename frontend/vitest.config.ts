import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // Playwright's permanent E2E suite lives in ./e2e and must never be picked
    // up by Vitest's default *.spec.ts include glob.
    exclude: ['e2e/**', 'node_modules/**'],
  },
})
