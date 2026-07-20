// TEMPORARY review config (not committed) — lets jakkaritw click through the
// REAL app (local source == deployed cc40d39) against the STAGING backend with
// real Fabric SQL data, impersonating a filler via the Easy-Auth-OFF spoof
// header. Delete this file after the review. Run:
//   npm run dev -- --config vite.review.config.ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const STAGING =
  'https://cman-budget-web-stg.kindstone-f34836dd.southeastasia.azurecontainerapps.io'
const SPOOF_USER = 'passakornh@chememan.com'

// Every proxied API call gets the spoof identity header injected so the
// browser (which cannot set it) is seen by staging as this filler.
function withSpoof(target: string) {
  return {
    target,
    changeOrigin: true,
    secure: true,
    configure: (proxy: any) => {
      proxy.on('proxyReq', (proxyReq: any) => {
        proxyReq.setHeader('x-ms-client-principal-name', SPOOF_USER)
      })
    },
  }
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5180,
    proxy: {
      '/health': withSpoof(STAGING),
      '/me': withSpoof(STAGING),
      '/scope': withSpoof(STAGING),
      '/budget': withSpoof(STAGING),
      '/approval': withSpoof(STAGING),
      '/attachments': withSpoof(STAGING),
      '/reference': withSpoof(STAGING),
    },
  },
})
