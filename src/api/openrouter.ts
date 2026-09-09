import type {
  GenerateRequest,
  GenerateResponse,
  ImageEndpoint,
  ImageModelListItem,
} from './types'

const BASE = 'https://openrouter.ai/api/v1'

function headers(apiKey: string) {
  return {
    Authorization: `Bearer ${apiKey}`,
    'Content-Type': 'application/json',
    'HTTP-Referer': 'https://localhost/openrouter-image-client',
    'X-Title': 'OpenRouter ImageGen UI',
  }
}

function errMsg(data: unknown, fallback: string): string {
  if (data && typeof data === 'object' && 'error' in data) {
    const e = (data as { error: { message?: string; code?: number } }).error
    return `Error ${e.code ?? ''}: ${e.message ?? fallback}`.trim()
  }
  return fallback
}

export async function listImageModels(apiKey: string): Promise<ImageModelListItem[]> {
  const res = await fetch(`${BASE}/images/models`, { headers: headers(apiKey) })
  const data = await res.json()
  if (!res.ok) throw new Error(errMsg(data, `获取模型列表失败 (${res.status})`))
  return (data.data ?? []) as ImageModelListItem[]
}

export async function listModelEndpoints(apiKey: string, modelId: string): Promise<ImageEndpoint[]> {
  const [author, ...rest] = modelId.split('/')
  const slug = rest.join('/')
  const res = await fetch(`${BASE}/images/models/${author}/${slug}/endpoints`, {
    headers: headers(apiKey),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(errMsg(data, `获取端点信息失败 (${res.status})`))
  return (data.endpoints ?? []) as ImageEndpoint[]
}

export async function generateImages(apiKey: string, body: GenerateRequest): Promise<GenerateResponse> {
  const res = await fetch(`${BASE}/images`, {
    method: 'POST',
    headers: headers(apiKey),
    body: JSON.stringify(body),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(errMsg(data, `生成失败 (${res.status})`))
  return data as GenerateResponse
}

export interface StreamEvent {
  type: string
  b64_json?: string
  partial_image_index?: number
  media_type?: string
  created?: number
  usage?: GenerateResponse['usage']
  error?: { message: string }
  text?: string
}

/** SSE 流式生成：onEvent 收到 partial/completed/error 事件 */
export async function generateImagesStream(
  apiKey: string,
  body: GenerateRequest,
  onEvent: (e: StreamEvent) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/images`, {
    method: 'POST',
    headers: headers(apiKey),
    body: JSON.stringify({ ...body, stream: true }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    throw new Error(errMsg(data, `生成失败 (${res.status})`))
  }
  if (!res.body) throw new Error('当前环境不支持流式读取')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      const t = line.trim()
      if (!t.startsWith('data:')) continue
      const payload = t.slice(5).trim()
      if (payload === '[DONE]') return
      try {
        onEvent(JSON.parse(payload) as StreamEvent)
      } catch {
        /* 忽略心跳注释 */
      }
    }
  }
}
