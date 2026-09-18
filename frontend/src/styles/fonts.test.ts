// Guards the self-hosted Prompt @font-face declarations against drift: every
// `src: url(...)` in fonts.css must point at a woff2 file that actually
// exists under public/fonts/prompt/, and every declared weight must have
// BOTH a thai and a latin face — otherwise a missing file means the browser
// silently falls back to the system font with no error (the exact failure
// mode this self-host replaces).
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const FONTS_CSS_PATH = resolve(process.cwd(), 'src/styles/fonts.css')
const PUBLIC_FONTS_DIR = resolve(process.cwd(), 'public/fonts/prompt')

interface FontFace {
  weight: number
  url: string
}

function parseFontFaces(cssText: string): FontFace[] {
  const faces: FontFace[] = []
  const blockRe = /@font-face\s*\{([^}]+)\}/g
  let block: RegExpExecArray | null
  while ((block = blockRe.exec(cssText)) !== null) {
    const body = block[1]
    const weightMatch = /font-weight:\s*(\d+)/.exec(body)
    const urlMatch = /url\((['"])(\/fonts\/prompt\/[^'"]+\.woff2)\1\)/.exec(body)
    if (weightMatch && urlMatch) {
      faces.push({ weight: Number(weightMatch[1]), url: urlMatch[2] })
    }
  }
  return faces
}

describe('fonts.css — self-hosted Prompt', () => {
  it('exists and declares at least one @font-face', () => {
    expect(existsSync(FONTS_CSS_PATH)).toBe(true)
    const cssText = readFileSync(FONTS_CSS_PATH, 'utf-8')
    const faces = parseFontFaces(cssText)
    expect(faces.length).toBeGreaterThan(0)
  })

  it('every declared src file exists under public/fonts/prompt/', () => {
    const cssText = readFileSync(FONTS_CSS_PATH, 'utf-8')
    const faces = parseFontFaces(cssText)
    for (const face of faces) {
      const filePath = resolve(process.cwd(), 'public' + face.url)
      expect(existsSync(filePath), `missing font file for ${face.url}`).toBe(true)
    }
  })

  it('every declared weight has both a thai and a latin face', () => {
    const cssText = readFileSync(FONTS_CSS_PATH, 'utf-8')
    const faces = parseFontFaces(cssText)
    const weights = [...new Set(faces.map((f) => f.weight))]
    expect(weights.length).toBeGreaterThan(0)
    for (const weight of weights) {
      const facesForWeight = faces.filter((f) => f.weight === weight)
      const hasThai = facesForWeight.some((f) => f.url.includes('-thai.woff2'))
      const hasLatin = facesForWeight.some((f) => f.url.includes('-latin.woff2'))
      expect(hasThai, `weight ${weight} missing thai face`).toBe(true)
      expect(hasLatin, `weight ${weight} missing latin face`).toBe(true)
    }
  })

  it('public/fonts/prompt/ directory exists (self-hosted, not a CDN link)', () => {
    expect(existsSync(PUBLIC_FONTS_DIR)).toBe(true)
  })
})
