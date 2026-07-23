import type { NextConfig } from 'next'

// Dev-only proxy parity with the old vite.config.ts. The A7 backend has NO
// `/api` prefix (routers mounted bare in backend/app/main.py), so each known
// route namespace is forwarded as-is. Rewrites exist only under `next dev`;
// the exported static site is served same-origin by FastAPI in production.
const BACKEND_DEV_SERVER = 'http://127.0.0.1:8000'

const nextConfig: NextConfig = {
  output: 'export',
  // No next/image use today; block the optimized-loader foot-gun for later.
  images: { unoptimized: true },
  async rewrites() {
    const namespaces = ['health', 'me', 'scope', 'budget', 'approval', 'attachments', 'reference']
    return namespaces.map((ns) => ({
      source: `/${ns}/:path*`,
      destination: `${BACKEND_DEV_SERVER}/${ns}/:path*`,
    }))
  },
}

export default nextConfig
