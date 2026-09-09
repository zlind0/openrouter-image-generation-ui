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

/** 全量覆盖保存。 */
export async function persistHistory(items: HistoryItem[]): Promise<void> {
  const db = await openDb()
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      const st = tx.objectStore(STORE)
      st.clear()
      for (const it of items) st.put(it)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } finally {
    db.close()
  }
}
