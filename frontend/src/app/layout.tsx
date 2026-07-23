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
    <html lang="th" data-theme="light">
      <head>
        {/* Fonts match the canonical mockup (design/mockups/0002claude design/0002.3budget-export.html).
            Plain <link>, NOT next/font — see gotcha G4. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400;1,6..72,500&family=Archivo:wght@400;500;600;700&family=IBM+Plex+Sans+Thai:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
        {/* Pre-paint theme sync (ARCH-a): layout.tsx hardcodes data-theme="light"
            above, and under dynamic(ssr:false) the whole App (and ThemeToggle's
            effect) mounts later than it did on Vite — without this, an
            opted-in dark-mode user sees a longer flash-of-light before the
            stored theme applies. Runs before first paint; static-export-safe
            (inline script ships in the exported HTML, no server needed). */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=localStorage.getItem('budget-theme');if(t==='dark')document.documentElement.dataset.theme='dark'}catch(e){}",
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  )
}
