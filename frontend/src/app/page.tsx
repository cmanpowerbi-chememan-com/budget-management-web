'use client'

import dynamic from 'next/dynamic'

// The whole app is client-only: App.tsx and the grid read window/localStorage
// in render-time initializers, and every screen sits behind Easy Auth, so a
// build-time prerender would crash (G1) while buying nothing (no SEO/public).
const App = dynamic(() => import('../App'), { ssr: false })

export default function Page() {
  return <App />
}
