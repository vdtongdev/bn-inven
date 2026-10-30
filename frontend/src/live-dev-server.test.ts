import { describe, expect, it } from 'vitest'

describe('running BN-Inven Vite server', () => {
  it('serves the current red remove-button styling', async () => {
    const response = await fetch('http://127.0.0.1:5173/src/App.tsx')
    expect(response.status).toBe(200)

    const appModule = await response.text()
    expect(appModule).toContain('bg-red-50')
    expect(appModule).toContain('text-red-700')
  })
})
