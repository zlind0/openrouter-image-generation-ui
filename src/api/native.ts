import { invoke, Channel, isTauri } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import type { ProxySettings } from './settings'

/** 是否跑在 Tauri 壳里；浏览器直接预览（npm run dev）时为 false，走 fetch/input/a[download] 降级 */
export const IN_TAURI = isTauri()

export interface ProxyWire {
  enabled: boolean
  /** 注意：Rust 侧 serde rename 要的是字面 `type`，嵌套对象不走大小写转换，必须原样发 */
  type: string
  url: string
  username: string
  password: string
}

/** 设置对象转 Rust 命令参数（TypeScript 里 `type` 作键名合法） */
export function proxyWire(p?: ProxySettings | null): ProxyWire | null {
  if (!p) return null
  return {
    enabled: p.enabled,
    type: p.type,
    url: p.url,
    username: p.username,
    password: p.password,
  }
}

export function isMacOS(): boolean {
  return /macintosh|mac os x/i.test(navigator.userAgent)
}

/* ---- 参考图：文件选择（Tauri 原生对话框 / 浏览器 input） ---- */
export async function pickImages(): Promise<Array<{ name: string; dataUrl: string }>> {
  if (IN_TAURI) return invoke('pick_images')
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.multiple = true
    input.onchange = () => {
      if (!input.files) {
        resolve([])
        return
      }
      const jobs = Array.from(input.files).map(
        (f) =>
          new Promise<{ name: string; dataUrl: string }>((res, rej) => {
            const rd = new FileReader()
            rd.onload = () => res({ name: f.name, dataUrl: String(rd.result) })
            rd.onerror = () => rej(new Error('读取文件失败'))
            rd.readAsDataURL(f)
          }),
      )
      Promise.all(jobs).then(resolve, () => resolve([]))
    }
    input.oncancel = () => resolve([])
    input.click()
  })
}

/* ---- 保存图片（Tauri 原生另存为 / 浏览器 a[download]） ---- */
export async function saveImage(payload: {
  b64: string
  mediaType?: string
  suggestedName?: string
}): Promise<{ saved: boolean; path?: string }> {
  if (IN_TAURI) {
    return invoke('save_image', {
      b64: payload.b64,
      mediaType: payload.mediaType,
      suggestedName: payload.suggestedName,
    })
  }
  const mime = payload.mediaType || 'image/png'
  const a = document.createElement('a')
  a.href = `data:${mime};base64,${payload.b64}`
  a.download = payload.suggestedName || `or-image-${Date.now()}.png`
  a.click()
  return { saved: false }
}

/* ---- 图片 URL 转 dataURL（Tauri 经 Rust+代理拉取 / 浏览器直连 fetch） ---- */
export async function fetchImageDataUrl(u: string, proxy?: ProxySettings | null): Promise<string> {
  if (IN_TAURI) {
    const r = await invoke<{ dataUrl: string }>('fetch_image_url', {
      url: u,
      proxy: proxyWire(proxy),
    })
    return r.dataUrl
  }
  const res = await fetch(u)
  if (!res.ok) throw new Error(`拉图失败 (${res.status})`)
  const blob = await res.blob()
  return new Promise((resolve, reject) => {
    const fr = new FileReader()
    fr.onload = () => resolve(String(fr.result))
    fr.onerror = () => reject(new Error('读取图片失败'))
    fr.readAsDataURL(blob)
  })
}

/* ---- 自绘标题栏窗口控制 ---- */
export const minimizeWin = () => invoke('win_minimize')
export const toggleMaxWin = () => invoke('win_toggle_maximize')
export const closeWin = () => invoke('win_close')
export const getMaxed = async (): Promise<boolean> => (IN_TAURI ? invoke('win_is_maximized') : false)
export function onMaxState(cb: (maxed: boolean) => void): void {
  if (!IN_TAURI) return
  void listen<boolean>('window:max-state', (e) => cb(e.payload))
}

export { Channel, isTauri }
