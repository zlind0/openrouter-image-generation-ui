/** Pure-web helpers (Tauri removed). File pick / download / URL fetch. */

export function isMacOS(): boolean {
  return /macintosh|mac os x/i.test(navigator.userAgent)
}

export async function pickImages(): Promise<Array<{ name: string; dataUrl: string }>> {
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*,.avif,.heic,.heif'
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

export async function saveImage(payload: {
  b64: string
  mediaType?: string
  suggestedName?: string
}): Promise<{ saved: boolean; path?: string }> {
  const mime = payload.mediaType || 'image/png'
  const b64 = payload.b64.includes(',') ? payload.b64.split(',')[1] : payload.b64
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  const blob = new Blob([bytes], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = payload.suggestedName || `or-image-${Date.now()}.png`
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
  return { saved: true }
}

export async function fetchImageDataUrl(u: string): Promise<string> {
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
