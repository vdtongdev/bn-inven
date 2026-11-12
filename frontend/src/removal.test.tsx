import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it.each([
  ['Pending', 200], ['Pending', 409], ['Approved', 200], ['Approved', 409],
])('removes a %s item only after DELETE succeeds (%s)', async (reviewStatus, status) => {
  let deleted = false
  const draft = { id: 'working-1', batch_id: 'batch-1', item_code: 'BN-1',
    product_name: 'Test label', review_status: reviewStatus }
  const confirm = vi.fn(() => true)
  vi.stubGlobal('confirm', confirm)
  const buttonName = reviewStatus === 'Approved' ? 'Xóa sản phẩm đã duyệt' : 'Loại bỏ sản phẩm'
  const request = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'DELETE') {
      deleted = status === 200
      return Response.json(deleted ? { deleted: true } : { detail: 'Recognition is running' }, { status })
    }
    if (url.endsWith('/batches')) return Response.json([{ id: 'batch-1' }])
    if (url.endsWith('/drafts')) return Response.json(deleted ? [] : [draft])
    return Response.json([])
  })
  vi.stubGlobal('fetch', request)
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: buttonName }))
  if (reviewStatus === 'Approved') expect(confirm).toHaveBeenCalledWith(expect.stringContaining('BN-1'))
  await waitFor(() => expect(request).toHaveBeenCalledWith(expect.stringContaining('/drafts/working-1'),
    expect.objectContaining({ method: 'DELETE' })))
  if (status === 200) {
    await waitFor(() => expect(screen.queryByRole('button', { name: buttonName })).not.toBeInTheDocument())
  } else {
    expect(await screen.findByText('Error: Recognition is running')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: buttonName })).toBeEnabled()
  }
})

it('keeps the approved item when deletion is canceled', async () => {
  vi.stubGlobal('confirm', vi.fn(() => false))
  const request = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/batches')) return Response.json([{ id: 'batch-1' }])
    if (url.endsWith('/drafts')) return Response.json([{
      id: 'approved-1', batch_id: 'batch-1', item_code: 'BN-1',
      product_name: 'Approved label', review_status: 'Approved',
    }])
    return Response.json([])
  })
  vi.stubGlobal('fetch', request)
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa sản phẩm đã duyệt' }))
  expect(request.mock.calls.every(([input]) => !String(input).includes('/api/drafts/'))).toBe(true)
  expect(screen.getByRole('button', { name: 'Xóa sản phẩm đã duyệt' })).toBeEnabled()
})
