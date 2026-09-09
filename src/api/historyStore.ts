import type { HistoryItem } from './types'

const DB_NAME = 'or-img-client'
const STORE = 'history'

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) {
        req.result.createObjectStore(STORE, { keyPath: 'id' })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

/** 读取全部历史（按 time 倒序）。base64 大图存 IndexedDB，避免 localStorage 配额问题。 */
export async function loadHistory(): Promise<HistoryItem[]> {
  const db = await openDb()
  try {
    const items = await new Promise<HistoryItem[]>((resolve, reject) => {
      const rq = db.transaction(STORE, 'readonly').objectStore(STORE).getAll()
      rq.onsuccess = () => resolve((rq.result ?? []) as HistoryItem[])
      rq.onerror = () => reject(rq.error)
    })
    return items.sort((a, b) => b.time - a.time)
  } finally {
    db.close()
  }
}

/** 去 Vue 响应式 Proxy，只保留纯 JSON 数据，保证 structured clone 可用。 */
function toStorable(items: HistoryItem[]): HistoryItem[] {
  return items.map((it) => ({
    id: String(it.id),
    time: Number(it.time),
    model: String(it.model ?? ''),
    prompt: String(it.prompt ?? ''),
    images: Array.isArray(it.images)
      ? it.images.map((img) => ({
          b64_json: String(img?.b64_json ?? ''),
          ...(img?.media_type ? { media_type: String(img.media_type) } : {}),
        }))
      : [],
    ...(it.usage ? { usage: JSON.parse(JSON.stringify(it.usage)) } : {}),
    ...(it.error ? { error: String(it.error) } : {}),
    ...(it.params ? { params: JSON.parse(JSON.stringify(it.params)) } : {}),
    ...(typeof it.providerChoice === 'string' ? { providerChoice: it.providerChoice } : {}),
    ...(Array.isArray(it.references)
      ? { references: it.references.map((r) => ({ name: String(r?.name ?? ''), dataUrl: String(r?.dataUrl ?? '') })) }
      : {}),
  })) as HistoryItem[]
}

/** 全量覆盖保存。 */
export async function persistHistory(items: HistoryItem[]): Promise<void> {
  // 先转纯对象：history.value 是 Vue 响应式 Proxy，直接 put 会报 could not be cloned
  const plain = toStorable(items)
  const db = await openDb()
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      const st = tx.objectStore(STORE)
      st.clear()
      for (const it of plain) st.put(it)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } finally {
    db.close()
  }
}
