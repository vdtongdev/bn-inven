import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => vi.unstubAllGlobals())

it.each([200, 409])('removes a working item only after DELETE succeeds (%s)', async status => {
  let deleted = false
  const draft = { id: 'working-1', batch_id: 'batch-1', item_code: 'BN-1',
    product_name: 'Test label', review_status: 'Pending' }
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
  fireEvent.click(await screen.findByRole('button', { name: 'Loại bỏ sản phẩm' }))
  await waitFor(() => expect(request).toHaveBeenCalledWith(expect.stringContaining('/drafts/working-1'),
    expect.objectContaining({ method: 'DELETE' })))
  if (status === 200) {
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Loại bỏ sản phẩm' })).not.toBeInTheDocument())
  } else {
    expect(await screen.findByText('Error: Recognition is running')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Loại bỏ sản phẩm' })).toBeInTheDocument()
  }
})
