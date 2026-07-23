/** The one place the build-system env contract lives (Vite import.meta.env →
 * Next process.env.NEXT_PUBLIC_*). Same-origin '' default (ADR-0004). */
export function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_BASE ?? ''
}
