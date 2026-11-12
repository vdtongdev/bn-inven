import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('deduplicates brand and name, exposes product type, and previews every edited component', async () => {
  const draft = {
    id: 'draft-1', batch_id: 'batch-1', item_code: 'BN-001',
    product_type: 'Sữa', product_name: ' VINAMILK ', brand: 'Vinamilk',
    primary_unit: 'Hộp', package_size: '1 L', review_status: 'Pending',
    extraction: { observed: { product_type: 'Sữa' } },
  }
  let savedPatch: Record<string, unknown> | undefined
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'PATCH') {
      savedPatch = JSON.parse(String(init.body))
      return Response.json({ ...draft, ...savedPatch, final_name: 'TH Ít đường Chai 500 ml' })
    }
    if (url.endsWith('/api/batches')) return Response.json([{ id: 'batch-1' }])
    if (url.endsWith('/drafts')) return Response.json([draft])
    return Response.json([])
  }))
  await act(async () => { render(<App />) })
  expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Sữa Vinamilk Hộp 1 L')
  fireEvent.change(screen.getByLabelText(/^Loại sản phẩm/), { target: { value: 'Sữa tươi' } })
  fireEvent.change(screen.getByLabelText(/^Tên sản phẩm/), { target: { value: 'Ít đường' } })
  fireEvent.change(screen.getByDisplayValue('Vinamilk'), { target: { value: 'TH' } })
  fireEvent.change(screen.getByDisplayValue('Hộp'), { target: { value: 'Chai' } })
  fireEvent.change(screen.getByDisplayValue('1 L'), { target: { value: '500 ml' } })
  expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Sữa tươi TH Ít đường Chai 500 ml')
  fireEvent.change(screen.getByLabelText(/^Loại sản phẩm/), { target: { value: '' } })
  expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('TH Ít đường Chai 500 ml')
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' })) })
  expect(savedPatch).toMatchObject({ product_type: '', product_name: 'Ít đường', brand: 'TH',
    primary_unit: 'Chai', package_size: '500 ml' })
  expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('TH Ít đường Chai 500 ml')
})
