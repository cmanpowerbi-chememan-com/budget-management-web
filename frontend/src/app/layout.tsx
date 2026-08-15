import type { Metadata, Viewport } from 'next'
import '../styles/tokens.css'
import '../styles/global.css'

export const metadata: Metadata = {
  title: 'Budget Management — Chememan',
  icons: { icon: '/favicon.svg' },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1.0,
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="th">
      <head>
        {/* Chememan theme (2026-08-15): --sans points at the system font stack
            (styles/tokens.css), so no webfont is loaded here. Previously loaded
            Newsreader/Archivo/IBM Plex via Google Fonts to match the canonical
            mockup — removed since nothing references them. */}
      </head>
      <body>{children}</body>
    </html>
  )
}
