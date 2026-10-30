import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

describe('catalog capture shell', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/export-profiles')) return Response.json([{ id: 'profile-1', code: 'GENERIC_DEMO', name: 'GENERIC / DEMO', is_demo: true }])
      if (url.endsWith('/api/batches') && init?.method === 'POST') return Response.json({ id: 'batch-1', name: 'Lô chụp mới', created_at: new Date().toISOString() }, { status: 201 })
      if (url.endsWith('/api/batches')) return Response.json([])
      if (url.endsWith('/api/batches/batch-1/drafts')) return Response.json([])
      return Response.json({})
    }))
  })

  it('creates a batch and exposes the mobile capture and upload choices', async () => {
    render(<App />)
    expect(await screen.findByText('Danh mục hàng hóa')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Tạo lô' }))
    expect(await screen.findByText('Lô chụp mới')).toBeInTheDocument()
    expect(screen.getByText('Chụp nhãn bằng camera')).toBeInTheDocument()
    expect(screen.getByText('Chọn ảnh từ thiết bị')).toBeInTheDocument()
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/batches'), expect.objectContaining({ method: 'POST' })))
  })
})
