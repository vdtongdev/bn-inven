import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => vi.unstubAllGlobals())

it('approves a product without a business item type', async () => {
  let draft = { id: 'draft-1', batch_id: 'batch-1', item_code: 'BN-1', product_name: 'Test item',
    product_type: 'Test type', primary_unit: 'cái', review_status: 'Pending' }
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/batches')) return Response.json([{ id: 'batch-1' }])
    if (url.endsWith('/drafts')) return Response.json([draft])
    if (init?.method === 'PATCH') {
      const patch = JSON.parse(String(init.body))
      expect(patch).not.toHaveProperty('item_type')
      draft = { ...draft, ...patch }
      return Response.json(draft)
    }
    if (url.endsWith('/approve')) {
      draft = { ...draft, review_status: 'Approved' }
      return Response.json(draft)
    }
    return Response.json([])
  }))
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'Kiểm tra hợp lệ và duyệt' }))
  expect(await screen.findByText('Approved')).toBeInTheDocument()
  expect(screen.queryByLabelText(/Loại hàng/)).not.toBeInTheDocument()
  expect(screen.getByLabelText(/Loại sản phẩm/)).toHaveValue('Test type')
})
