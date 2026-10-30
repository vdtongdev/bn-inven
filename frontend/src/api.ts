const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const response = await fetch(`${apiBase}${path}`, { ...init, headers, credentials: 'include' })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.detail?.message ?? payload.detail ?? `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

export { apiBase }
