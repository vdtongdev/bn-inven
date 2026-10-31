import { useEffect, useRef, useState } from 'react'
import { api, apiUrl } from './api'
import type { Batch, Draft, ExportProfile } from './types'

const fields: { key: keyof Draft; label: string }[] = [
  { key: 'product_name', label: 'Tên sản phẩm' }, { key: 'brand', label: 'Thương hiệu' },
  { key: 'primary_unit', label: 'Đơn vị tính' }, { key: 'package_size', label: 'Quy cách đóng gói' },
]

let internalBatchPromise: Promise<Batch> | null = null

function normalizeTitlePart(value: string | null | undefined) {
  return (value ?? '').normalize('NFC').trim().replace(/\s+/g, ' ').toLocaleLowerCase('vi')
}

function itemTitle(draft: Draft) {
  const productType = String(draft.extraction?.observed.product_type ?? '').trim()
  const productName = draft.product_name?.trim() ?? ''
  if (!productType) return productName || 'Chưa đọc được tên sản phẩm'

  const sameAsType = normalizeTitlePart(productName) === normalizeTitlePart(productType)
  const titleParts = [productType]
  if (draft.brand?.trim()) titleParts.push(draft.brand.trim())
  if (!sameAsType && productName) titleParts.push(productName)
  if (draft.primary_unit?.trim()) titleParts.push(draft.primary_unit.trim())
  if (draft.package_size?.trim()) titleParts.push(draft.package_size.trim())
  return titleParts.join(' ')
}

function createInternalBatchOnce() {
  if (!internalBatchPromise) {
    internalBatchPromise = api<Batch>('/api/batches', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'Danh mục' }),
    }).catch(error => {
      internalBatchPromise = null
      throw error
    })
  }
  return internalBatchPromise
}

export default function App() {
  const [batch, setBatch] = useState<Batch | null>(null)
  const [serverDrafts, setDrafts] = useState<Draft[]>([])
  const [edits, setEdits] = useState<Record<string, Partial<Draft>>>({})
  const refreshVersion = useRef(0)
  const nextRefreshId = useRef(0)
  const appliedRefreshId = useRef(0)
  const pendingSaves = useRef(new Set<string>())
  const [approvingIds, setApprovingIds] = useState<string[]>([])
  const drafts = serverDrafts.map(draft => draft.review_status === 'Approved' ? draft : { ...draft, ...edits[draft.id] })
  const [profiles, setProfiles] = useState<ExportProfile[]>([])
  const [online, setOnline] = useState(navigator.onLine)
  const [busy, setBusy] = useState(false)
  const [processingJobId, setProcessingJobId] = useState<string | null>(null)
  const [message, setMessage] = useState('')

  async function refreshBatches() {
    const version = refreshVersion.current
    const refreshId = ++nextRefreshId.current
    const rows = await api<Batch[]>('/api/batches')
    const uploadBatch = rows[0] ?? await createInternalBatchOnce()
    const allBatches = rows.length > 0 ? rows : [uploadBatch]
    setBatch(uploadBatch)
    const draftGroups = await Promise.all(allBatches.map(row => api<Draft[]>(`/api/batches/${row.id}/drafts`)))
    if (version === refreshVersion.current && refreshId > appliedRefreshId.current) {
      appliedRefreshId.current = refreshId
      setDrafts(draftGroups.flat().filter(draft => draft.review_status !== 'Excluded'))
    }
  }
  useEffect(() => {
    const onlineHandler = () => setOnline(navigator.onLine)
    window.addEventListener('online', onlineHandler); window.addEventListener('offline', onlineHandler)
    void Promise.all([refreshBatches(), api<ExportProfile[]>('/api/export-profiles').then(setProfiles)]).catch(e => setMessage(String(e)))
    return () => { window.removeEventListener('online', onlineHandler); window.removeEventListener('offline', onlineHandler) }
  }, [])
  useEffect(() => {
    if (!batch) return
    const timer = window.setInterval(() => { void refreshBatches().catch(e => setMessage(String(e))) }, 2500)
    return () => window.clearInterval(timer)
  }, [batch?.id])

  async function upload(file?: File, draftId?: string) {
    if (!batch || !file) return
    setBusy(true); setMessage('Đang lưu ảnh và xếp hàng nhận dạng…')
    try {
      const targetBatchId = draftId ? drafts.find(row => row.id === draftId)?.batch_id ?? batch.id : batch.id
      const form = new FormData(); form.append('file', file); if (draftId) form.append('draft_id', draftId)
      const result = await api<{ job_id: string }>(`/api/batches/${targetBatchId}/photos`, { method: 'POST', body: form })
      setProcessingJobId(result.job_id)
      setMessage('Đã lưu ảnh. Đang nhận dạng…')
      while (true) {
        const job = await api<{ status: string; last_error: string | null }>(`/api/jobs/${result.job_id}`)
        if (job.status === 'Succeeded') {
          setMessage('Đã nhận dạng ảnh thành công.')
          await refreshBatches()
          break
        }
        if (job.status === 'Failed') {
          setMessage(`Nhận dạng ảnh thất bại${job.last_error ? `: ${job.last_error}` : '.'}`)
          break
        }
        await new Promise(resolve => window.setTimeout(resolve, 1000))
      }
    } catch (e) { setMessage(String(e)) } finally { setBusy(false); setProcessingJobId(null) }
  }

  async function saveDraft(draft: Draft, patch: Partial<Draft>) {
    if (pendingSaves.current.has(draft.id)) return
    pendingSaves.current.add(draft.id)
    try {
      const updated = await api<Draft>(`/api/drafts/${draft.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) })
      refreshVersion.current++
      setEdits(current => {
        const remaining = { ...current[draft.id] }
        for (const key of Object.keys(patch) as (keyof Draft)[]) {
          if (remaining[key] === patch[key]) delete remaining[key]
        }
        return { ...current, [draft.id]: remaining }
      })
      setDrafts(current => current.map(row => row.id === draft.id ? updated : row)); setMessage('Đã lưu bản nháp.')
    } catch (e) { setMessage(String(e)) } finally { pendingSaves.current.delete(draft.id) }
  }
  async function removeDraft(draft: Draft) {
    try {
      await api<Draft>(`/api/drafts/${draft.id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ review_status: 'Excluded' }),
      })
      refreshVersion.current++
      setDrafts(current => current.filter(row => row.id !== draft.id))
      setMessage('Đã loại bỏ sản phẩm khỏi danh sách.')
    } catch (e) { setMessage(String(e)) }
  }
  async function approve(draft: Draft) {
    if (pendingSaves.current.has(draft.id)) return
    pendingSaves.current.add(draft.id)
    setApprovingIds(current => [...current, draft.id])
    try {
      await api<Draft>(`/api/drafts/${draft.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ product_name: draft.product_name, brand: draft.brand, model_number: draft.model_number, barcode: draft.barcode, item_type: draft.item_type, category_code: draft.category_code, primary_unit: draft.primary_unit, package_size: draft.package_size }) })
      const updated = await api<Draft>(`/api/drafts/${draft.id}/approve`, { method: 'POST' })
      refreshVersion.current++
      setEdits(current => { const remaining = { ...current }; delete remaining[draft.id]; return remaining })
      setDrafts(current => current.map(row => row.id === draft.id ? updated : row)); setMessage('Đã duyệt sản phẩm vào danh mục.')
    } catch (e) { setMessage(String(e)) } finally {
      pendingSaves.current.delete(draft.id)
      setApprovingIds(current => current.filter(id => id !== draft.id))
    }
  }
  async function exportApproved() {
    const approved = drafts.filter(d => d.review_status === 'Approved')
    if (!approved.length) { setMessage('Chưa có sản phẩm đã duyệt để xuất.'); return }
    try {
      const profile = profiles[0]
      const result = await api<{ id: string; filename: string }>('/api/exports', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ profile_id: profile.id, draft_ids: approved.map(d => d.id) }) })
      const response = await fetch(apiUrl(`/api/exports/${result.id}/download`), { credentials: 'include' })
      if (!response.ok) throw new Error(`Tải file lỗi: HTTP ${response.status}`)
      const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a'); link.href = url; link.download = result.filename; link.click(); URL.revokeObjectURL(url)
      setMessage(`Đã tải ${result.filename}. Đây là file DEMO, chưa xác nhận nhập được vào MISA.`)
    } catch (e) { setMessage(String(e)) }
  }

  return <main className="mx-auto max-w-5xl px-4 py-5 sm:px-6">
    <header className="mb-6 flex items-start justify-between gap-4"><div><p className="text-sm font-semibold uppercase tracking-wide text-teal-700">BN-Inven</p><h1 className="text-2xl font-bold">Danh mục hàng hóa</h1><p className="text-sm text-slate-600">Chụp nhãn · rà soát · xuất Excel</p></div><span className={`rounded-full px-3 py-1 text-sm ${online ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-900'}`}>{online ? 'Đang trực tuyến' : 'Ngoại tuyến'}</span></header>
    <nav className="mb-5 flex gap-2 border-b pb-3"><a className="tab" href="#capture">Chụp sản phẩm</a><a className="tab" href="#review">Rà soát ({drafts.length})</a></nav>
    {message && <div role="status" className="mb-4 rounded-lg bg-slate-100 p-3 text-sm">{message}</div>}
    <section id="capture" className="card mb-5"><h2 className="section-title">Chụp sản phẩm</h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="capture-button">Chụp nhãn bằng camera<input className="sr-only" type="file" accept="image/*" capture="environment" disabled={busy || !online || !batch} onChange={e => void upload(e.target.files?.[0])} /></label><label className="capture-button">Chọn ảnh từ thiết bị<input className="sr-only" type="file" accept="image/jpeg,image/png,image/webp" disabled={busy || !online || !batch} onChange={e => void upload(e.target.files?.[0])} /></label><p className="sm:col-span-2 text-xs text-slate-500">Ảnh lưu trên máy chủ. Cần Internet để nhận dạng; PWA chỉ lưu giao diện cơ bản khi ngoại tuyến.</p></div>
      {processingJobId && <p role="status" aria-live="polite" className="mt-3 flex items-center gap-2 text-sm text-teal-800"><span aria-hidden="true" className="inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent" />Đang xử lý ảnh…</p>}
    </section>
    <section id="review" className="mb-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="section-title">Rà soát sản phẩm</h2>
        <button className="secondary" disabled={!drafts.some(d => d.review_status === 'Approved')} onClick={() => void exportApproved()}>Xuất Excel DEMO</button>
      </div>
      {drafts.length === 0 ? <p className="muted">Chưa có bản nháp. Tải ảnh nhãn để bắt đầu.</p> :
        <div className="grid gap-4 md:grid-cols-2">
          {drafts.map(draft => <article className="card" key={draft.id}>
            <div className="mb-3 flex items-start justify-between">
              <div><h3 className="font-semibold">{itemTitle(draft)}</h3><p className="text-xs text-slate-500">Mã BN: {draft.item_code}</p></div>
              <span className="status">{draft.review_status}</span>
            </div>
            {(draft.photo_ids?.length ? draft.photo_ids : draft.photo_id ? [draft.photo_id] : []).map(photoId => <img key={photoId} className="mb-3 max-h-56 w-full rounded-lg object-contain bg-slate-100" src={apiUrl(`/api/photos/${photoId}/image`)} alt="Ảnh nhãn sản phẩm" />)}
            {draft.duplicate_suggestion && <p role="alert" className="mb-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Phát hiện trùng {draft.duplicate_suggestion.kind === 'exact_barcode' ? 'mã vạch' : 'mã model'} với {draft.duplicate_suggestion.scope === 'catalog' ? 'danh mục đã duyệt' : 'bản nháp khác'} ({draft.duplicate_suggestion.item_code}). Cần người dùng xác nhận; hệ thống chưa gộp sản phẩm.</p>}
            {draft.extraction && <p className="mb-3 text-xs text-slate-500">Nguồn: {draft.extraction.provider} / {draft.extraction.model}. Đề xuất AI cần người xác nhận.</p>}
            <div className="grid gap-2">{fields.map(field => <label className="grid gap-1 text-sm" key={field.key}><span>{field.label}{!draft[field.key] && <span className="ml-1 text-amber-700">· cần kiểm tra</span>}</span><input className="input" value={String(draft[field.key] ?? '')} disabled={draft.review_status === 'Approved' || approvingIds.includes(draft.id)} onChange={e => { const value = e.target.value; setEdits(current => ({ ...current, [draft.id]: { ...current[draft.id], [field.key]: value } })) }} /></label>)}</div>
            {draft.review_status !== 'Approved' && <>
              <label className="secondary mt-3 flex cursor-pointer justify-center">Thêm ảnh cho sản phẩm<input className="sr-only" type="file" accept="image/*" capture="environment" disabled={busy || !online} onChange={e => void upload(e.target.files?.[0], draft.id)} /></label>
              <button className="secondary mt-2 w-full" onClick={() => void saveDraft(draft, { product_name: draft.product_name, brand: draft.brand, model_number: draft.model_number, barcode: draft.barcode, item_type: draft.item_type, category_code: draft.category_code, primary_unit: draft.primary_unit, package_size: draft.package_size })}>Lưu thay đổi</button>
              <button className="primary mt-2 w-full" onClick={() => void approve(draft)}>Kiểm tra hợp lệ và duyệt</button>
              <button className="secondary mt-2 w-full border-red-300 bg-red-50 text-red-700 hover:bg-red-100" onClick={() => void removeDraft(draft)}>Loại bỏ sản phẩm</button>
            </>}
          </article>)}
        </div>}
    </section>
    <footer className="mt-5 text-center text-xs text-slate-500">Tệp xuất hiện tại dùng cấu hình GENERIC/DEMO, không phải mẫu MISA chính thức.</footer>
  </main>
}
