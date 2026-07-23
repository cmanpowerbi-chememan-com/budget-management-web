/** Guarded `window.location` reads/writes — the browser-I/O half of the
 * platform seam (env.ts is the other half). `ssr:false` (app/page.tsx)
 * already makes every render-time call site safe, but centralizing the
 * `typeof window` guard here keeps that safety in one audited place instead
 * of re-checked ad hoc at each call site. */
export function currentSearch(): string {
  return typeof window === 'undefined' ? '' : window.location.search
}
export function currentHref(): string {
  return typeof window === 'undefined' ? '' : window.location.href
}
export function navigate(url: string): void {
  if (typeof window !== 'undefined') window.location.href = url
}
