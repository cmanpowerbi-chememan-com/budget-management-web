import type { Metadata, Viewport } from 'next'
import '../styles/tokens.css'
import '../styles/fonts.css'
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
        {/* Chememan theme (2026-08-15, CI palette 2026-08-21; font swap
            2026-09-18): the CI font FC Minimal is licensed and not available
            to self-host, so jakkaritw chose Prompt (Cadson Demak, SIL Open
            Font License, Google Fonts) as the free stand-in — every user now
            renders the SAME font, not their machine's system default. Prompt
            is SELF-HOSTED under public/fonts/prompt/ (fetched once via
            setup/fetch_prompt_font.py, licence text alongside the files) and
            loaded via ../styles/fonts.css — there is still NO Google Fonts /
            CDN `<link>` here. "No external requests at runtime" remains
            intentional; only the font FILES moved from "not shipped" to
            "shipped in this repo". Swapping in the real FC Minimal later =
            replace the files under public/fonts/prompt/ and the @font-face
            family name in fonts.css / tokens.css --sans. */}
      </head>
      <body>{children}</body>
    </html>
  )
}
