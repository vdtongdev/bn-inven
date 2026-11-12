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
    if (Array.isArray(payload.detail?.fields)) {
      const labels: Record<string, string> = {
        product_name: 'Tên sản phẩm', item_type: 'Loại hàng', primary_unit: 'Đơn vị tính',
      }
      const missing = payload.detail.fields.map((field: string) => labels[field] ?? field)
      throw new Error(`${payload.detail.message}: ${missing.join(', ')}`)
    }
    throw new Error(payload.detail?.message ?? payload.detail ?? `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

export { apiBase }
