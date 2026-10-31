import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

it('keeps unsaved field edits across the periodic server refresh', async () => {
  vi.useFakeTimers()
  const draft = {
    id: 'draft-1', batch_id: 'batch-1', item_code: 'BN-001',
    product_name: 'Original name', brand: 'Original brand', primary_unit: 'Box',
    package_size: '10 pieces', review_status: 'NeedsReview', photo_ids: [],
  }
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/batches')) return Response.json([{ id: 'batch-1' }])
    if (url.endsWith('/drafts')) return Response.json([draft])
    return Response.json([])
  }))
  await act(async () => { render(<App />) })

  fireEvent.change(screen.getByDisplayValue('Original name'), { target: { value: 'Tên mới' } })
  fireEvent.change(screen.getByDisplayValue('Original brand'), { target: { value: '' } })
  expect(screen.getByDisplayValue('Tên mới')).toBeInTheDocument()

  await act(async () => { await vi.advanceTimersByTimeAsync(2500) })

  expect(screen.getByDisplayValue('Tên mới')).toBeInTheDocument()
  expect(screen.queryByDisplayValue('Original brand')).not.toBeInTheDocument()
})

it('keeps newer typing during save, rejects a stale poll, and sends the edit on retry', async () => {
  vi.useFakeTimers()
  let serverDraft = {
    id: 'draft-1', batch_id: 'batch-1', item_code: 'BN-001', product_name: 'Original',
    brand: 'Brand', primary_unit: 'Box', package_size: '10', review_status: 'NeedsReview', photo_ids: [],
  }
  let resolveSave!: (response: Response) => void
  let resolvePoll!: (response: Response) => void
  let draftReads = 0
  const patches: Record<string, unknown>[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/batches')) return Response.json([{ id: 'batch-1' }])
    if (url.endsWith('/drafts')) {
      if (++draftReads === 2) return new Promise<Response>(resolve => { resolvePoll = resolve })
      return Response.json([serverDraft])
    }
    if (init?.method === 'PATCH') {
      patches.push(JSON.parse(String(init.body)))
      if (patches.length === 1) return new Promise<Response>(resolve => { resolveSave = resolve })
      if (patches.length === 2) return Response.json({ detail: 'Temporary failure' }, { status: 500 })
      serverDraft = { ...serverDraft, ...patches.at(-1) }
      return Response.json(serverDraft)
    }
    return Response.json([])
  }))
  await act(async () => { render(<App />) })
  fireEvent.change(screen.getByDisplayValue('Original'), { target: { value: 'First edit' } })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' })) })
  await act(async () => { await vi.advanceTimersByTimeAsync(2500) })
  fireEvent.change(screen.getByDisplayValue('First edit'), { target: { value: 'Newer edit' } })
  const staleDraft = { ...serverDraft }
  serverDraft = { ...serverDraft, product_name: 'First edit' }
  await act(async () => { resolveSave(Response.json(serverDraft)) })
  await act(async () => { resolvePoll(Response.json([staleDraft])) })
  expect(screen.getByDisplayValue('Newer edit')).toBeInTheDocument()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' })) })
  await act(async () => { await vi.advanceTimersByTimeAsync(2500) })
  expect(screen.getByDisplayValue('Newer edit')).toBeInTheDocument()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' })) })
  expect(patches.at(-1)?.product_name).toBe('Newer edit')
  serverDraft = { ...serverDraft, product_name: 'Later server update', brand: 'New brand' }
  await act(async () => { await vi.advanceTimersByTimeAsync(2500) })
  expect(screen.getByDisplayValue('Later server update')).toBeInTheDocument()
  expect(screen.getByDisplayValue('New brand')).toBeInTheDocument()
})

it('does not revert a saved value when an older refresh finishes afterward', async () => {
  vi.useFakeTimers()
  const draft = { id: 'draft-1', batch_id: 'batch-1', item_code: 'BN-001', product_name: 'Original', review_status: 'NeedsReview' }
  let resolvePoll!: (response: Response) => void
  let reads = 0
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/batches')) return Response.json([{ id: 'batch-1' }])
    if (url.endsWith('/drafts')) {
      if (++reads === 2) return new Promise<Response>(resolve => { resolvePoll = resolve })
      return Response.json([draft])
    }
    if (init?.method === 'PATCH') return Response.json({ ...draft, ...JSON.parse(String(init.body)) })
    return Response.json([])
  }))
  await act(async () => { render(<App />) })
  await act(async () => { await vi.advanceTimersByTimeAsync(2500) })
  fireEvent.change(screen.getByDisplayValue('Original'), { target: { value: 'Saved edit' } })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' })) })
  await act(async () => { resolvePoll(Response.json([draft])) })
  expect(screen.getByDisplayValue('Saved edit')).toBeInTheDocument()
})

it('applies slow overlapping polls without letting older responses overwrite newer data', async () => {
  vi.useFakeTimers()
  const draft = { id: 'draft-1', batch_id: 'batch-1', item_code: 'BN-001', product_name: 'Original', review_status: 'NeedsReview' }
  const polls: ((response: Response) => void)[] = []
  let reads = 0
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/batches')) return Response.json([{ id: 'batch-1' }])
    if (url.endsWith('/drafts')) {
      if (++reads === 1) return Response.json([draft])
      return new Promise<Response>(resolve => { polls.push(resolve) })
    }
    return Response.json([])
  }))
  await act(async () => { render(<App />) })
  await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
  await act(async () => { polls[0](Response.json([{ ...draft, product_name: 'Slow update' }])) })
  expect(screen.getByDisplayValue('Slow update')).toBeInTheDocument()
  await act(async () => { await vi.advanceTimersByTimeAsync(2500) })
  await act(async () => { polls[2](Response.json([{ ...draft, product_name: 'Newest update' }])) })
  await act(async () => { polls[1](Response.json([{ ...draft, product_name: 'Older update' }])) })
  expect(screen.getByDisplayValue('Newest update')).toBeInTheDocument()
})

it('submits edited approval values and unlocks retained edits if approval fails', async () => {
  vi.useFakeTimers()
  const draft = { id: 'draft-1', batch_id: 'batch-1', item_code: 'BN-001', product_name: 'Original', review_status: 'NeedsReview' }
  let resolveApproval!: (response: Response) => void
  let patch: Record<string, unknown> = {}
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/batches')) return Response.json([{ id: 'batch-1' }])
    if (url.endsWith('/drafts')) return Response.json([draft])
    if (init?.method === 'PATCH') {
      patch = JSON.parse(String(init.body))
      return Response.json({ ...draft, ...patch })
    }
    if (url.endsWith('/approve')) return new Promise<Response>(resolve => { resolveApproval = resolve })
    return Response.json([])
  }))
  await act(async () => { render(<App />) })
  fireEvent.change(screen.getByDisplayValue('Original'), { target: { value: 'Edited for approval' } })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra hợp lệ và duyệt' })) })
  expect(patch.product_name).toBe('Edited for approval')
  expect(screen.getByDisplayValue('Edited for approval')).toBeDisabled()
  await act(async () => { resolveApproval(Response.json({ detail: 'Missing required unit' }, { status: 422 })) })
  await act(async () => { await vi.advanceTimersByTimeAsync(2500) })
  expect(screen.getByDisplayValue('Edited for approval')).not.toBeDisabled()
  expect(screen.getByRole('button', { name: 'Kiểm tra hợp lệ và duyệt' })).toBeInTheDocument()
})
