const apiBase = import.meta.env.VITE_API_BASE_URL ?? '/api'

export function apiUrl(path: string): string {
  const base = apiBase.replace(/\/+$/, '')
  const endpoint = base.endsWith('/api') && (path === '/api' || path.startsWith('/api/'))
    ? path.slice('/api'.length)
    : path
  return `${base}${endpoint}`
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const response = await fetch(apiUrl(path), { ...init, headers, credentials: 'include' })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.detail?.message ?? payload.detail ?? `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

export { apiBase }
