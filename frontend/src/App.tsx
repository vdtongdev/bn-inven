import { useEffect, useState } from 'react'
import { api, apiBase } from './api'
import type { Batch, Draft, ExportProfile } from './types'

const fields: { key: keyof Draft; label: string }[] = [
  { key: 'product_name', label: 'Tên sản phẩm' }, { key: 'brand', label: 'Thương hiệu' },
  { key: 'model_number', label: 'Mã model / mã NSX' }, { key: 'barcode', label: 'Mã vạch' },
  { key: 'item_type', label: 'Loại hàng hóa / dịch vụ' }, { key: 'category_code', label: 'Nhóm hàng gợi ý' },
  { key: 'primary_unit', label: 'Đơn vị tính' }, { key: 'package_size', label: 'Quy cách đóng gói' },
]

export default function App() {
  const [batches, setBatches] = useState<Batch[]>([])
  const [batch, setBatch] = useState<Batch | null>(null)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [profiles, setProfiles] = useState<ExportProfile[]>([])
  const [name, setName] = useState('Lô chụp mới')
  const [online, setOnline] = useState(navigator.onLine)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  async function refreshBatches() {
    const rows = await api<Batch[]>('/api/batches'); setBatches(rows)
    if (batch) {
      const fresh = rows.find(row => row.id === batch.id)
      if (fresh) setBatch(fresh)
      setDrafts(await api<Draft[]>(`/api/batches/${batch.id}/drafts`))
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

  async function createBatch() {
    setBusy(true); setMessage('')
    try {
      const created = await api<Batch>('/api/batches', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) })
      setBatch(created); setDrafts([]); setMessage('Đã tạo lô chụp.')
      setBatches(await api<Batch[]>('/api/batches'))
    } catch (e) { setMessage(String(e)) } finally { setBusy(false) }
  }

  async function upload(file?: File, draftId?: string) {
    if (!batch || !file) return
    setBusy(true); setMessage('Đang lưu ảnh và xếp hàng nhận dạng…')
    try {
      const form = new FormData(); form.append('file', file); if (draftId) form.append('draft_id', draftId)
      const result = await api<{ job_id: string }>(`/api/batches/${batch.id}/photos`, { method: 'POST', body: form })
      setMessage(`Đã lưu ảnh. Tác vụ nhận dạng: ${result.job_id.slice(0, 8)}.`)
      await refreshBatches()
    } catch (e) { setMessage(String(e)) } finally { setBusy(false) }
  }

  async function saveDraft(draft: Draft, patch: Partial<Draft>) {
    try {
      const updated = await api<Draft>(`/api/drafts/${draft.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) })
      setDrafts(current => current.map(row => row.id === draft.id ? updated : row)); setMessage('Đã lưu bản nháp.')
    } catch (e) { setMessage(String(e)) }
  }
  async function approve(draft: Draft) {
    try {
      await api<Draft>(`/api/drafts/${draft.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ product_name: draft.product_name, brand: draft.brand, model_number: draft.model_number, barcode: draft.barcode, item_type: draft.item_type, category_code: draft.category_code, primary_unit: draft.primary_unit, package_size: draft.package_size }) })
      const updated = await api<Draft>(`/api/drafts/${draft.id}/approve`, { method: 'POST' })
      setDrafts(current => current.map(row => row.id === draft.id ? updated : row)); setMessage('Đã duyệt sản phẩm vào danh mục.')
    } catch (e) { setMessage(String(e)) }
  }
  async function exportApproved() {
    if (!batch) return
    const approved = drafts.filter(d => d.review_status === 'Approved')
    if (!approved.length) { setMessage('Chưa có sản phẩm đã duyệt để xuất.'); return }
    try {
      const profile = profiles[0]
      const result = await api<{ id: string; filename: string }>('/api/exports', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ profile_id: profile.id, draft_ids: approved.map(d => d.id) }) })
      const response = await fetch(`${apiBase}/api/exports/${result.id}/download`, { credentials: 'include' })
      if (!response.ok) throw new Error(`Tải file lỗi: HTTP ${response.status}`)
      const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a'); link.href = url; link.download = result.filename; link.click(); URL.revokeObjectURL(url)
      setMessage(`Đã tải ${result.filename}. Đây là file DEMO, chưa xác nhận nhập được vào MISA.`)
    } catch (e) { setMessage(String(e)) }
  }

  return <main className="mx-auto max-w-5xl px-4 py-5 sm:px-6">
    <header className="mb-6 flex items-start justify-between gap-4"><div><p className="text-sm font-semibold uppercase tracking-wide text-teal-700">BN-Inven</p><h1 className="text-2xl font-bold">Danh mục hàng hóa</h1><p className="text-sm text-slate-600">Chụp nhãn · rà soát · xuất Excel</p></div><span className={`rounded-full px-3 py-1 text-sm ${online ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-900'}`}>{online ? 'Đang trực tuyến' : 'Ngoại tuyến'}</span></header>
    <nav className="mb-5 flex gap-2 border-b pb-3"><a className="tab" href="#capture">Chụp sản phẩm</a><a className="tab" href="#review">Rà soát ({drafts.length})</a><a className="tab" href="#batches">Các lô</a></nav>
    {message && <div role="status" className="mb-4 rounded-lg bg-slate-100 p-3 text-sm">{message}</div>}
    <section id="capture" className="card mb-5"><h2 className="section-title">Lô chụp hiện tại</h2>{batch ? <div className="flex flex-wrap items-center justify-between gap-3"><div><strong>{batch.name}</strong><p className="text-sm text-slate-600">{batch.photo_count} ảnh · {batch.draft_count} bản nháp</p></div><button className="secondary" onClick={() => { setBatch(null); setDrafts([]) }}>Đổi lô</button></div> : <div className="flex flex-col gap-2 sm:flex-row"><input className="input flex-1" aria-label="Tên lô chụp" value={name} onChange={e => setName(e.target.value)} /><button className="primary" disabled={busy} onClick={() => void createBatch()}>Tạo lô</button></div>}
      {batch && <div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="capture-button">Chụp nhãn bằng camera<input className="sr-only" type="file" accept="image/*" capture="environment" disabled={busy || !online} onChange={e => void upload(e.target.files?.[0])} /></label><label className="capture-button">Chọn ảnh từ thiết bị<input className="sr-only" type="file" accept="image/jpeg,image/png,image/webp" disabled={busy || !online} onChange={e => void upload(e.target.files?.[0])} /></label><p className="sm:col-span-2 text-xs text-slate-500">Ảnh lưu trên máy chủ. Cần Internet để nhận dạng; PWA chỉ lưu giao diện cơ bản khi ngoại tuyến.</p></div>}</section>
    <section id="review" className="mb-5"><div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h2 className="section-title">Rà soát sản phẩm</h2><button className="secondary" disabled={!drafts.some(d => d.review_status === 'Approved')} onClick={() => void exportApproved()}>Xuất Excel DEMO</button></div>{!batch ? <p className="muted">Chọn hoặc tạo lô để xem sản phẩm.</p> : drafts.length === 0 ? <p className="muted">Chưa có bản nháp. Tải ảnh nhãn để bắt đầu.</p> : <div className="grid gap-4 md:grid-cols-2">{drafts.map(draft => <article className="card" key={draft.id}><div className="mb-3 flex items-start justify-between"><div><h3 className="font-semibold">{draft.product_name || 'Chưa đọc được tên sản phẩm'}</h3><p className="text-xs text-slate-500">Mã BN: {draft.item_code}</p></div><span className="status">{draft.review_status}</span></div>{(draft.photo_ids?.length ? draft.photo_ids : draft.photo_id ? [draft.photo_id] : []).map(photoId => <img key={photoId} className="mb-3 max-h-56 w-full rounded-lg object-contain bg-slate-100" src={`${apiBase}/api/photos/${photoId}/image`} alt="Ảnh nhãn sản phẩm" />)}{draft.duplicate_suggestion && <p role="alert" className="mb-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Phát hiện trùng {draft.duplicate_suggestion.kind === 'exact_barcode' ? 'mã vạch' : 'mã model'} với {draft.duplicate_suggestion.scope === 'catalog' ? 'danh mục đã duyệt' : 'bản nháp trong lô'} ({draft.duplicate_suggestion.item_code}). Cần người dùng xác nhận; hệ thống chưa gộp sản phẩm.</p>}{draft.extraction && <p className="mb-3 text-xs text-slate-500">Nguồn: {draft.extraction.provider} / {draft.extraction.model}. Đề xuất AI cần người xác nhận.</p>}<div className="grid gap-2">{fields.map(field => <label className="grid gap-1 text-sm" key={field.key}><span>{field.label}{!draft[field.key] && <span className="ml-1 text-amber-700">· cần kiểm tra</span>}</span><input className="input" value={String(draft[field.key] ?? '')} disabled={draft.review_status === 'Approved'}  onChange={e => setDrafts(current => current.map(row => row.id === draft.id ? { ...row, [field.key]: e.target.value } : row))} /></label>)}</div>{draft.review_status !== 'Approved' && <><label className="secondary mt-3 flex cursor-pointer justify-center">Thêm ảnh cho sản phẩm<input className="sr-only" type="file" accept="image/*" capture="environment" disabled={busy || !online} onChange={e => void upload(e.target.files?.[0], draft.id)} /></label><button className="secondary mt-2 w-full" onClick={() => void saveDraft(draft, { product_name: draft.product_name, brand: draft.brand, model_number: draft.model_number, barcode: draft.barcode, item_type: draft.item_type, category_code: draft.category_code, primary_unit: draft.primary_unit, package_size: draft.package_size })}>Lưu thay đổi</button><button className="primary mt-2 w-full" onClick={() => void approve(draft)}>Kiểm tra hợp lệ và duyệt</button></>}</article>)}</div>}</section>
    <section id="batches" className="card"><h2 className="section-title mb-3">Các lô gần đây</h2>{batches.length === 0 ? <p className="muted">Chưa có lô chụp.</p> : <ul className="divide-y">{batches.map(row => <li key={row.id}><button className="flex w-full items-center justify-between py-3 text-left" onClick={async () => { setBatch(row); setDrafts(await api<Draft[]>(`/api/batches/${row.id}/drafts`)) }}><span className="font-medium">{row.name}</span><span className="text-sm text-slate-500">{row.photo_count} ảnh · {row.draft_count} sản phẩm</span></button></li>)}</ul>}</section>
    <footer className="mt-5 text-center text-xs text-slate-500">Tệp xuất hiện tại dùng cấu hình GENERIC/DEMO, không phải mẫu MISA chính thức.</footer>
  </main>
}
