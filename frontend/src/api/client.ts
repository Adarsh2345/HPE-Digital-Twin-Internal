const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

/** Turn a FastAPI `detail` payload (string, list of error items, or plain object) into readable text. */
function stringifyDetail(detail: unknown): string | undefined {
  if (detail === undefined || detail === null) return undefined
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === 'object' && item !== null && 'message' in item)
        ? String((item as { message: unknown }).message)
        : String(item))
      .join(' ')
  }
  if (typeof detail === 'object') {
    const obj = detail as Record<string, unknown>
    if (typeof obj.message === 'string') return obj.message
    if (typeof obj.error === 'string') return obj.error
    return JSON.stringify(detail)
  }
  return String(detail)
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function api<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const url = `${API_BASE}${path}`
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  let data: unknown
  const text = await res.text()
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }

  if (!res.ok) {
    const detail = stringifyDetail(
      typeof data === 'object' && data !== null && 'detail' in data
        ? (data as { detail: unknown }).detail
        : undefined,
    ) ?? res.statusText
    throw new ApiError(detail, res.status, data)
  }

  return data as T
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`)
    return res.ok
  } catch {
    return false
  }
}
