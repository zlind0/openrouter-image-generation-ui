import axios from 'axios'
import { ref } from 'vue'

export const api = axios.create({ baseURL: '', withCredentials: true })

let access = localStorage.getItem('access_token') || ''
/* 登录态变化计数器：让顶栏 v-if 即时响应登录/退出（access 本身非响应式） */
export const authTick = ref(0)

export function setToken(t: string) {
  access = t
  if (t) localStorage.setItem('access_token', t)
  else localStorage.removeItem('access_token')
  authTick.value++
}
export function getToken() {
  return access
}

api.interceptors.request.use((cfg) => {
  if (access) cfg.headers.Authorization = `Bearer ${access}`
  return cfg
})

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const orig = err.config
    if (err.response?.status === 401 && !orig._retried) {
      orig._retried = true
      try {
        const r = await axios.post('/api/auth/refresh', {}, { withCredentials: true })
        setToken(r.data.access_token)
        orig.headers.Authorization = `Bearer ${r.data.access_token}`
        return api(orig)
      } catch {
        setToken('')
        location.hash = '#/login'
      }
    }
    throw err
  },
)

// ---- 文件读取令牌：<img> 发不出 Authorization 头，故拼 ?token=（aud=files，仅能读图） ----
let fileToken = ''
let fileTokenExp = 0

export async function getFileToken(force = false): Promise<string> {
  if (!force && fileToken && Date.now() < fileTokenExp - 60_000) return fileToken
  const r = await api.get('/api/auth/file-token')
  fileToken = r.data.token
  fileTokenExp = Date.now() + (r.data.expires_in ?? 1800) * 1000
  return fileToken
}

/** 给需要鉴权的图片 URL 拼上文件令牌（列表缩略图、点开展示的原图） */
export function fileSrc(url: string): string {
  if (!url || !fileToken) return url
  return url + (url.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(fileToken)
}

// ---- OpenRouter proxy (Key 永不落地前端) ----
export const orApi = {
  models: () => api.get('/api/openrouter/models').then((r) => r.data.data ?? r.data),
  endpoints: (id: string) => {
    const [author, ...rest] = id.split('/')
    return api.get(`/api/openrouter/models/${author}/${rest.join('/')}/endpoints`).then((r) => r.data.endpoints ?? []);
  },
  generate: (body: object) => api.post('/api/openrouter/images', body).then((r) => r.data),
  keyInfo: () => api.get('/api/openrouter/key').then((r) => r.data.data ?? r.data),
}
