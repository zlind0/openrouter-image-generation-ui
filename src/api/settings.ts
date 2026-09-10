export type ProxyType = 'http' | 'https' | 'socks5'

export interface ProxySettings {
  enabled: boolean
  type: ProxyType
  /** 主机:端口，可带 scheme，如 127.0.0.1:7890 / http://127.0.0.1:7890 */
  url: string
  username: string
  password: string
}

export interface AppSettings {
  baseUrl: string
  apiKey: string
  proxy: ProxySettings
}

export const DEFAULT_BASE_URL = 'https://openrouter.ai/api/v1'
const LS_SETTINGS = 'or-img-settings'
const LS_LEGACY_KEY = 'or-img-api-key'

export function defaultSettings(): AppSettings {
  return {
    baseUrl: DEFAULT_BASE_URL,
    apiKey: '',
    proxy: { enabled: false, type: 'http', url: '', username: '', password: '' },
  }
}

export function loadSettings(): AppSettings {
  const d = defaultSettings()
  try {
    const raw = localStorage.getItem(LS_SETTINGS)
    if (raw) {
      const s = JSON.parse(raw) as Partial<AppSettings>
      return {
        baseUrl: (s.baseUrl || d.baseUrl).trim().replace(/\/+$/, ''),
        apiKey: (s.apiKey || '').trim(),
        proxy: {
          enabled: !!s.proxy?.enabled,
          type: s.proxy?.type === 'https' || s.proxy?.type === 'socks5' ? s.proxy.type : 'http',
          url: (s.proxy?.url || '').trim(),
          username: (s.proxy?.username || '').trim(),
          password: s.proxy?.password || '',
        },
      }
    }
  } catch { /* 损坏则回退默认 */ }
  // 兼容旧版本：顶栏 Key 存 or-img-api-key
  try {
    const legacy = (localStorage.getItem(LS_LEGACY_KEY) || '').trim()
    if (legacy) {
      d.apiKey = legacy
      localStorage.removeItem(LS_LEGACY_KEY)
      saveSettings(d)
    }
  } catch { /* ignore */ }
  return d
}

export function saveSettings(s: AppSettings): void {
  const clean: AppSettings = {
    baseUrl: (s.baseUrl || DEFAULT_BASE_URL).trim().replace(/\/+$/, ''),
    apiKey: (s.apiKey || '').trim(),
    proxy: {
      enabled: !!s.proxy.enabled,
      type: s.proxy.type,
      url: (s.proxy.url || '').trim(),
      username: (s.proxy.username || '').trim(),
      password: s.proxy.password || '',
    },
  }
  localStorage.setItem(LS_SETTINGS, JSON.stringify(clean))
}

/** 把用户填的 url 归一化成 host:port（去掉 scheme 和末尾 /） */
export function normalizeProxyHostPort(url: string): string {
  let u = (url || '').trim()
  u = u.replace(/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//, '').replace(/\/+$/, '')
  return u
}

const LS_LAST_MODEL = 'or-img-last-model'

/** 上次“选择过”的模型（下拉选中即记，不要求实际生成过） */
export function loadLastModel(): string {
  try {
    return localStorage.getItem(LS_LAST_MODEL) || ''
  } catch {
    return ''
  }
}

export function saveLastModel(id: string): void {
  try {
    if (id) localStorage.setItem(LS_LAST_MODEL, id)
  } catch { /* ignore */ }
}
