import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => vi.unstubAllGlobals())

it('lets a reviewer fill the missing item type and approve the item', async () => {
  let draft = { id: 'draft-1', batch_id: 'batch-1', item_code: 'BN-1', product_name: 'Test item',
    primary_unit: 'cái', item_type: null as string | null, review_status: 'Pending' }
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/batches')) return Response.json([{ id: 'batch-1' }])
    if (url.endsWith('/drafts')) return Response.json([draft])
    if (init?.method === 'PATCH') {
      draft = { ...draft, ...JSON.parse(String(init.body)) }
      return Response.json(draft)
    }
    if (url.endsWith('/approve')) {
      if (!draft.item_type) return Response.json({ detail: {
        message: 'Draft is missing required fields', fields: ['item_type'],
      } }, { status: 422 })
      draft = { ...draft, review_status: 'Approved' }
      return Response.json(draft)
    }
    return Response.json([])
  }))
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'Kiểm tra hợp lệ và duyệt' }))
  expect(await screen.findByText('Error: Draft is missing required fields: Loại hàng')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText(/Loại hàng/), { target: { value: 'Hàng hóa' } })
  fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra hợp lệ và duyệt' }))
  expect(await screen.findByText('Approved')).toBeInTheDocument()
})
