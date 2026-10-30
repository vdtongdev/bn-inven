import { afterEach, describe, expect, it, vi } from 'vitest'

describe('browser API routing', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('requests the current origin API without duplicating its path prefix', async () => {
    vi.stubEnv('VITE_API_BASE_URL', undefined)
    const fetchMock = vi.fn(async () => Response.json([]))
    vi.stubGlobal('fetch', fetchMock)
    const { api, apiBase } = await import('./api')

    await api('/api/batches')

    expect(apiBase).toBe('/api')
    expect(fetchMock).toHaveBeenCalledWith('/api/batches', expect.any(Object))
  })

  it.each(['', 'https://catalog.example'])('keeps an explicit API origin override: %s', async base => {
    vi.stubEnv('VITE_API_BASE_URL', base)
    const fetchMock = vi.fn(async () => Response.json([]))
    vi.stubGlobal('fetch', fetchMock)
    const { api } = await import('./api')

    await api('/api/batches')

    expect(fetchMock).toHaveBeenCalledWith(`${base}/api/batches`, expect.any(Object))
  })

  it('uses the same URL construction for photo previews and workbook downloads', async () => {
    vi.stubEnv('VITE_API_BASE_URL', undefined)
    const { apiUrl } = await import('./api')

    expect(apiUrl('/api/photos/photo-1/image')).toBe('/api/photos/photo-1/image')
    expect(apiUrl('/api/exports/export-1/download')).toBe('/api/exports/export-1/download')
  })

  it('accepts an API base path override without repeating /api', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://catalog.example/api/')
    const { apiUrl } = await import('./api')

    expect(apiUrl('/api/batches')).toBe('https://catalog.example/api/batches')
  })
})
