// OpenRouter Image API 类型（依据 https://openrouter.ai/docs/guides/overview/multimodal/image-generation ）
export type CapabilityDescriptor =
  | { type: 'enum'; values: string[] }
  | { type: 'range'; min: number; max: number }
  | { type: 'boolean' }

export interface ImageModelArchitecture {
  input_modalities: string[]
  output_modalities: string[]
}

export interface ImageModelListItem {
  id: string
  name: string
  description: string
  created: number
  architecture: ImageModelArchitecture
  supported_parameters: Record<string, CapabilityDescriptor>
  supports_streaming: boolean
  endpoints: string // 相对 URL，如 /api/v1/images/models/xxx/endpoints
}

export interface ImagePricingEntry {
  billable: string
  unit: string
  cost_usd: number
  variant?: string
}

export interface ImageEndpoint {
  provider_name: string
  provider_slug: string
  provider_tag: string | null
  supported_parameters: Record<string, CapabilityDescriptor>
  allowed_passthrough_parameters: string[]
  supports_streaming: boolean
  pricing: ImagePricingEntry[]
}

export interface ReferenceImage {
  name: string
  dataUrl: string // data:...;base64,... 或 http(s) URL
}

export interface GenerateRequest {
  model: string
  prompt: string
  n?: number
  resolution?: string
  aspect_ratio?: string
  size?: string
  quality?: string
  output_format?: string
  background?: string
  output_compression?: number
  seed?: number
  stream?: boolean
  input_references?: Array<{ type: 'image_url'; image_url: { url: string } }>
  provider?: {
    only?: string[]
    order?: string[]
    ignore?: string[]
    sort?: string
    allow_fallbacks?: boolean
    options?: Record<string, Record<string, unknown>>
  }
  user?: string
}

export interface GeneratedImage {
  b64_json: string
  media_type?: string
}

export interface GenerateResponse {
  created: number
  data: GeneratedImage[]
  usage?: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    cost?: number
  }
}

export interface HistoryItem {
  id: string
  time: number
  model: string
  prompt: string
  images: GeneratedImage[]
  usage?: GenerateResponse['usage']
  error?: string
}
