import { useEffect, useRef, useState } from 'react'
import { fetchAttachments, fetchDownloadUrl, uploadAttachment } from '../api/attachments'
import { ApiError } from '../api/client'
import type { AttachmentInfo } from '../api/types'

export interface AttachmentsModalProps {
  department: string
  fiscalYear: number
  /** Fill-scope-or-admin on this department (the server re-checks this on
   * every upload regardless — this only shows/hides the upload control). */
  canUpload: boolean
  onClose: () => void
}

const ACCEPT = '.pdf,.xlsx,.xls,.png,.jpg,.jpeg'

function describeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return `${err.message}${err.detail ? ` (${err.detail})` : ''}`
  return fallback
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

/** SharePoint attachments per (ฝ่าย, fiscal_year) — spec R1. No local DB
 * table: the file list IS what SharePoint's folder currently holds, listed
 * fresh on open and after every upload. */
export function AttachmentsModal({ department, fiscalYear, canUpload, onClose }: AttachmentsModalProps) {
  const [items, setItems] = useState<AttachmentInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  async function load() {
    setLoading(true)
    setLoadError(null)
    try {
      const result = await fetchAttachments(department, fiscalYear)
      setItems(result)
    } catch (err) {
      setLoadError(describeError(err, 'โหลดรายการไฟล์แนบไม่สำเร็จ กรุณาลองใหม่อีกครั้ง'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [department, fiscalYear])

  async function handleFilePicked(file: File) {
    setUploading(true)
    setActionError(null)
    try {
      await uploadAttachment(department, fiscalYear, file)
      await load()
    } catch (err) {
      setActionError(describeError(err, 'แนบไฟล์ไม่สำเร็จ'))
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function handleDownload(item: AttachmentInfo) {
    setActionError(null)
    try {
      const url = await fetchDownloadUrl(department, fiscalYear, item.item_id)
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      setActionError(describeError(err, 'เปิดไฟล์ไม่สำเร็จ'))
    }
  }

  return (
    <div className="modal-backdrop open" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" data-testid="attachments-modal">
        <div className="modal-head">
          <div>
            <h2 className="modal-title">
              ไฟล์แนบ <em>ฝ่าย {department}</em>
            </h2>
            <p className="modal-subtitle">ปีงบประมาณ {fiscalYear} · เอกสาร ฝ่าย/{department}/{fiscalYear}/</p>
          </div>
          <button type="button" className="modal-close" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          {actionError && (
            <div className="grid-error" role="alert" data-testid="attachments-action-error">
              <span>{actionError}</span>
            </div>
          )}

          {canUpload && (
            <label className="attach-drop">
              <input
                ref={fileInputRef}
                type="file"
                className="hidden-file"
                accept={ACCEPT}
                disabled={uploading}
                data-testid="attachments-upload-input"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) handleFilePicked(file)
                }}
              />
              <div className="hint">
                <b>{uploading ? 'กำลังอัปโหลด…' : 'คลิกเพื่อเลือกไฟล์'}</b> — เก็บเข้าโฟลเดอร์ฝ่าย/ปี ด้านบน
              </div>
              <div className="types">pdf · xlsx · xls · png · jpg — สูงสุด 10 MB</div>
            </label>
          )}

          {loading && <div className="grid-loading">กำลังโหลดรายการไฟล์แนบ…</div>}

          {!loading && loadError && (
            <div className="grid-error" role="alert">
              <span>{loadError}</span>
              <button type="button" className="btn" onClick={load}>
                ลองใหม่
              </button>
            </div>
          )}

          {!loading && !loadError && (
            <table className="attach-table" data-testid="attachments-list">
              <thead>
                <tr>
                  <th>ไฟล์</th>
                  <th>ขนาด</th>
                  <th>อัปโหลดโดย</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.length === 0 && (
                  <tr>
                    <td colSpan={4}>
                      <div className="attach-empty">ยังไม่มีไฟล์ในโฟลเดอร์นี้ — เลือกไฟล์เพื่อแนบ</div>
                    </td>
                  </tr>
                )}
                {items.map((item) => (
                  <tr key={item.item_id} data-testid={`attachments-item-${item.item_id}`}>
                    <td className="fname">{item.name}</td>
                    <td>{formatBytes(item.size)}</td>
                    <td>{item.created_by ?? '—'}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button type="button" className="btn" onClick={() => handleDownload(item)}>
                        เปิด/ดาวน์โหลด
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="modal-foot">
          <div className="modal-foot-info">ไฟล์ในโฟลเดอร์: {items.length}</div>
          <div className="modal-actions">
            <button type="button" className="btn" onClick={onClose}>
              ปิด
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
