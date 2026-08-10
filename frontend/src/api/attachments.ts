/** Typed calls to the A10 attachments endpoints (SharePoint, spec R1) —
 * built on the shared `apiFetch`. No caching/state here — `AttachmentsModal`
 * owns that. */
import { apiFetch } from './client'
import type { AttachmentInfo } from './types'

/** `GET /attachments` — files already in `<ฝ่าย>/<year>/`. */
export function fetchAttachments(department: string, fiscalYear: number): Promise<AttachmentInfo[]> {
  const params = new URLSearchParams({ department, fiscal_year: String(fiscalYear) })
  return apiFetch<AttachmentInfo[]>(`/attachments?${params.toString()}`)
}

/** `POST /attachments/upload` (multipart) — validated server-side (allowed
 * extensions + 10MB cap); the caller must Fill (or be admin for) the
 * department. */
export function uploadAttachment(department: string, fiscalYear: number, file: File): Promise<AttachmentInfo> {
  const form = new FormData()
  form.set('department', department)
  form.set('fiscal_year', String(fiscalYear))
  form.set('file', file)
  return apiFetch<AttachmentInfo>('/attachments/upload', { method: 'POST', body: form })
}

/** `GET /attachments/download-url` — a pre-authenticated, time-limited Graph
 * URL the caller opens directly (no file bytes stream through this backend). */
export function fetchDownloadUrl(department: string, fiscalYear: number, itemId: string): Promise<string> {
  const params = new URLSearchParams({ department, fiscal_year: String(fiscalYear), item_id: itemId })
  return apiFetch<{ url: string }>(`/attachments/download-url?${params.toString()}`).then((r) => r.url)
}

/** `DELETE /attachments` — removes one file from `<ฝ่าย>/<year>/` and returns
 * its name. Requires Fill-or-admin on the department (a See-only reviewer may
 * read the documents but not delete them), and the server refuses any item_id
 * that does not actually live in that folder. */
export function deleteAttachment(department: string, fiscalYear: number, itemId: string): Promise<string> {
  const params = new URLSearchParams({ department, fiscal_year: String(fiscalYear), item_id: itemId })
  return apiFetch<{ deleted: boolean; name: string }>(`/attachments?${params.toString()}`, {
    method: 'DELETE',
  }).then((r) => r.name)
}
