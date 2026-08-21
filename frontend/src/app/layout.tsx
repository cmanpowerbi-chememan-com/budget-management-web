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
        {/* Chememan theme (2026-08-15, CI palette 2026-08-21): --sans declares
            the CI-documented names ("FC Minimal", "IBM Plex Sans Thai", "Noto
            Sans Thai") first, then falls back to the system font stack
            (styles/tokens.css) — NO webfont `<link>` here, deliberately. None
            of the CI names are installed on a typical machine and the DS repo
            no longer ships assets/fonts to self-host, so almost every user
            still renders the system fallback (Segoe UI / San Francisco /
            etc.), same as before this change. Previously loaded
            Newsreader/Archivo/IBM Plex via Google Fonts to match the canonical
            mockup — removed since nothing references them; do not reintroduce
            a CDN font link, "no external requests" is intentional. */}
      </head>
      <body>{children}</body>
    </html>
  )
}
