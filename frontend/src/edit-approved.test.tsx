import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

function setup(status = 200) {
  let draft = { id: 'approved-1', batch_id: 'batch-1', item_code: 'BN-1',
    product_type: 'Sữa', brand: 'TH', product_name: 'Ít đường', primary_unit: 'Hộp',
    package_size: '1 L', final_name: 'Sữa TH Ít đường Hộp 1 L', review_status: 'Approved' }
  const request = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'PATCH') {
      if (status !== 200) return Response.json({ detail: 'Invalid product fields' }, { status })
      draft = { ...draft, ...JSON.parse(String(init.body)), final_name: 'Sữa TH Không đường Hộp 1 L' }
      return Response.json(draft)
    }
    if (url.endsWith('/batches')) return Response.json([{ id: 'batch-1' }])
    if (url.endsWith('/drafts')) return Response.json([draft])
    return Response.json([])
  })
  vi.stubGlobal('fetch', request)
  render(<App />)
  return request
}

it('unlocks approved fields and persists the updated title on save', async () => {
  const request = setup()
  const edit = await screen.findByRole('button', { name: 'Chỉnh sửa sản phẩm' })
  expect(screen.getByDisplayValue('Ít đường')).toBeDisabled()
  fireEvent.click(edit)
  expect(screen.getByDisplayValue('Ít đường')).toBeEnabled()
  fireEvent.change(screen.getByDisplayValue('Ít đường'), { target: { value: 'Không đường' } })
  expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Sữa TH Không đường Hộp 1 L')
  fireEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' }))
  await screen.findByRole('button', { name: 'Chỉnh sửa sản phẩm' })
  expect(request).toHaveBeenCalledWith(expect.stringContaining('/drafts/approved-1'),
    expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ product_name: 'Không đường' }) }))
  expect(screen.getByDisplayValue('Không đường')).toBeDisabled()
  expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Sữa TH Không đường Hộp 1 L')
})

it('discards unsaved edits and restores the saved title on cancel', async () => {
  const request = setup()
  fireEvent.click(await screen.findByRole('button', { name: 'Chỉnh sửa sản phẩm' }))
  fireEvent.change(screen.getByDisplayValue('Ít đường'), { target: { value: 'Không đường' } })
  fireEvent.click(screen.getByRole('button', { name: 'Hủy chỉnh sửa' }))
  expect(screen.getByDisplayValue('Ít đường')).toBeDisabled()
  expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Sữa TH Ít đường Hộp 1 L')
  expect(request.mock.calls.some(([, init]) => init?.method === 'PATCH')).toBe(false)
})

it('retains edits after a failed save so they can be corrected', async () => {
  setup(422)
  fireEvent.click(await screen.findByRole('button', { name: 'Chỉnh sửa sản phẩm' }))
  fireEvent.change(screen.getByDisplayValue('Ít đường'), { target: { value: 'Không đường' } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' }))
  expect(await screen.findByText('Error: Invalid product fields')).toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Lưu thay đổi' })).toBeEnabled())
  expect(screen.getByDisplayValue('Không đường')).toBeEnabled()
})
