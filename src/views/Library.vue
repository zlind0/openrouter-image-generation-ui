<template>
  <div class="lib">
    <div class="left">
      <h2>素材管理</h2>
      <div class="row"><h3>文件夹</h3><el-button size="small" @click="newFolder">新建</el-button></div>
      <el-tree :data="tree" :props="{label:'name',children:'children'}" @node-click="(d:any)=>{folderFilter=d.id;load()}" highlight-current />
      <el-button size="small" text @click="folderFilter='';load()">全部文件</el-button>
      <div class="row" style="margin-top:12px"><h3>上传</h3></div>
      <input ref="fileInput" type="file" multiple accept="image/*,.avif,.heic,.heif" style="display:none" @change="onPick" />
      <input ref="dirInput" type="file" webkitdirectory style="display:none" @change="onPickDir" />
      <el-button size="small" @click="fileInput?.click()">上传文件</el-button>
      <el-button size="small" @click="dirInput?.click()">按文件夹上传</el-button>
      <el-input v-model="uploadTags" placeholder="标签，逗号分隔" style="margin-top:8px" />
      <p class="hint">未选文件夹时默认进入「上传素材」库。按文件夹上传会按相对路径自动建树。支持 AVIF/HEIC，旧浏览器由服务端自动转 JPEG 兜底。</p>
    </div>
    <div class="right">
      <div class="filters">
        <el-input v-model="q" placeholder="文件名搜索" clearable style="width:180px" @change="load" />
        <el-input v-model="tags" placeholder="标签 a,b" clearable style="width:180px" @change="load" />
        <el-select v-model="match" style="width:110px" @change="load"><el-option label="标签AND" value="all" /><el-option label="标签OR" value="any" /></el-select>
        <el-input v-model="make" placeholder="EXIF: Canon/Sony…" clearable style="width:180px" @change="load" />
        <el-input-number v-model="isoMin" placeholder="ISO min" controls-position="right" style="width:130px" @change="load" />
        <el-input v-model="uploader" placeholder="上传者" clearable style="width:130px" @change="load" />
        <el-button @click="load">筛选</el-button>
      </div>
      <div class="grid">
        <el-card v-for="a in assets" :key="a.id" class="card">
          <el-image :src="srcOf(a,'thumb_url')" fit="cover" style="width:100%;height:160px" :preview-src-list="[srcOf(a,'file_url')]" title="缩略图，点击加载原图" @error="onImgError(a)" />
          <div class="fn">{{ a.filename }}</div>
          <div class="meta">{{ a.width }}×{{ a.height }} · {{ a.owner }} · {{ (a.exif.Make||'')+' '+(a.exif.Model||'') }}</div>
          <div class="tags"><el-tag v-for="t in a.tags" :key="t" size="small" style="margin:2px">{{ t }}</el-tag></div>
          <div class="ops">
            <el-button size="small" @click="openEdit(a)">标签/移动</el-button>
            <el-button size="small" @click="makeShare(a)">公开链接</el-button>
            <el-button size="small" type="danger" @click="remove(a)">删除</el-button>
          </div>
          <div v-if="a.mime==='image/avif'" class="hint">AVIF：Firefox 等旧端访问自动返回 JPEG（<a :href="compatUrl(a)" target="_blank">预览兜底</a>）</div>
        </el-card>
      </div>
    </div>
    <el-dialog v-model="editOpen" title="编辑素材" width="420px">
      <el-input v-model="editTags" placeholder="标签逗号分隔" />
      <el-select v-model="editFolder" clearable placeholder="移动到文件夹" style="width:100%;margin-top:8px">
        <el-option v-for="f in folders" :key="f.id" :label="f.path" :value="f.id" />
      </el-select>
      <template #footer><el-button type="primary" @click="saveEdit">保存</el-button></template>
    </el-dialog>
    <el-dialog v-model="shareOpen" title="图床公开链接" width="520px">
      <p>可在任意网页 <code>&lt;img src="URL"&gt;</code> 引用。访问会被统计 IP/次数，可随时撤销。</p>
      <el-button size="small" @click="createShare">生成新链接</el-button>
      <div v-for="s in shares" :key="s.id" class="share-row">
        <code>{{ shareUrl(s) }}</code>
        <span>访问 {{ s.view_count }} 次 {{ s.revoked ? '（已撤销）' : '' }}</span>
        <el-button size="small" @click="showStats(s)">统计</el-button>
        <el-button size="small" type="danger" @click="revoke(s)" :disabled="s.revoked">撤销</el-button>
      </div>
      <div v-if="stats" style="margin-top:8px"><h4>访问统计（总 {{ stats.view_count }}）</h4>
        <div v-for="(c,ip) in stats.by_ip" :key="ip">{{ ip }}: {{ c }} 次</div>
      </div>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, getFileToken } from '../api/client'

const folders = ref<any[]>([])
const assets = ref<any[]>([])
const folderFilter = ref('')
const q = ref(''), tags = ref(''), match = ref('all'), make = ref(''), uploader = ref('')
const isoMin = ref<number | undefined>(undefined)
const uploadTags = ref('')
const fileInput = ref<HTMLInputElement|null>(null)
const dirInput = ref<HTMLInputElement|null>(null)
const editOpen = ref(false), editTags = ref(''), editFolder = ref(''), editing = ref<any>(null)
const shareOpen = ref(false), shares = ref<any[]>([]), sharing = ref<any>(null), stats = ref<any>(null)
// <img> 发不出 Authorization 头，图片 URL 拼 ?token= 文件令牌（aud=files，仅能读图）
const ftoken = ref('')
const imgRetried = new Set<string>()
function srcOf(a: any, field: 'thumb_url' | 'file_url'): string {
  const u = a[field] || ''
  return ftoken.value ? u + (u.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(ftoken.value) : u
}
async function ensureFileToken(force = false) {
  try { ftoken.value = await getFileToken(force) } catch { /* 未登录时保持空，拦截器会跳登录 */ }
}
function compatUrl(a: any): string {
  const base = srcOf(a, 'file_url')
  return base + (base.includes('?') ? '&' : '?') + 'compat=1'
}
function onImgError(a: any) {
  // 令牌过期等导致 401 时刷新一次令牌并重载（每图仅重试一次防循环）
  if (imgRetried.has(a.id)) return
  imgRetried.add(a.id)
  ensureFileToken(true)
}

const tree = computed(() => {
  const map: Record<string, any> = {}
  folders.value.forEach((f) => (map[f.id] = { ...f, children: [] }))
  const roots: any[] = []
  folders.value.forEach((f) => { if (f.parent_id && map[f.parent_id]) map[f.parent_id].children.push(map[f.id]); else roots.push(map[f.id]) })
  return roots
})

async function loadFolders() { folders.value = (await api.get('/api/assets/folders')).data }
async function load() {
  const p: any = {}
  if (folderFilter.value) p.folder_id = folderFilter.value
  if (q.value) p.q = q.value
  if (tags.value) { p.tags = tags.value; p.match = match.value }
  if (make.value) p.make = make.value
  if (isoMin.value) p.iso_min = isoMin.value
  if (uploader.value) p.uploader = uploader.value
  assets.value = (await api.get('/api/assets', { params: p })).data
}
async function newFolder() {
  const { value } = await ElMessageBox.prompt('文件夹名（可用 a/b 建多级）', '新建文件夹')
  if (!value) return
  const parts = String(value).split('/').filter(Boolean)
  let parent: string | undefined
  for (const name of parts) {
    const path = folders.value.find((f) => f.id === parent)?.path
    try {
      const r = await api.post('/api/assets/folders', { name, parent_id: parent })
      parent = r.data.id
    } catch { const hit = folders.value.find((f) => f.name === name && (f.parent_id || undefined) === parent); if (hit) parent = hit.id }
  }
  await loadFolders()
}
async function doUpload(files: FileList, folderPath = '') {
  const fd = new FormData()
  Array.from(files).forEach((f) => fd.append('files', f))
  if (folderFilter.value) fd.append('folder_id', folderFilter.value)
  if (folderPath) fd.append('folder_path', folderPath)
  if (uploadTags.value) fd.append('tags', uploadTags.value)
  try {
    const r = await api.post('/api/assets/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    const saved = r.data.assets ?? []
    const skipped = r.data.skipped ?? []
    if (skipped.length) {
      ElMessage.warning(`成功 ${saved.length} 张，跳过 ${skipped.length} 个：${skipped.map((s: any) => s.filename).slice(0, 5).join('、')}${skipped.length > 5 ? '…' : ''}`)
    } else {
      ElMessage.success(`上传成功 ${saved.length} 张`)
    }
    load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || e.message || '上传失败')
  }
}
function onPick(e: Event) { const el = e.target as HTMLInputElement; if (el.files?.length) doUpload(el.files); el.value = '' }
function onPickDir(e: Event) {
  const el = e.target as HTMLInputElement
  if (!el.files?.length) return
  // 取公共前缀作为 folder_path，逐文件上传时后端按该树建文件夹
  const first = (el.files[0] as any).webkitRelativePath || ''
  const root = first.split('/')[0]
  doUpload(el.files, root); el.value = ''
}
function openEdit(a: any) { editing.value = a; editTags.value = a.tags.join(','); editFolder.value = a.folder_id || ''; editOpen.value = true }
async function saveEdit() {
  await api.patch(`/api/assets/${editing.value.id}`, { tags: editTags.value.split(',').map((s) => s.trim()).filter(Boolean), folder_id: editFolder.value || null })
  editOpen.value = false; load()
}
async function remove(a: any) {
  await ElMessageBox.confirm(`删除 ${a.filename}？`, '确认', { type: 'warning' })
  await api.delete(`/api/assets/${a.id}`); load()
}
async function makeShare(a: any) { sharing.value = a; shareOpen.value = true; stats.value = null; await reloadShares() }
async function reloadShares() { shares.value = (await api.get('/api/shares')).data.filter((s: any) => s.asset_id === sharing.value.id) }
async function createShare() { await api.post(`/api/assets/${sharing.value.id}/shares`, {}); reloadShares() }
function shareUrl(s: any) { return `${location.origin}${s.url}` }
async function showStats(s: any) { stats.value = (await api.get(`/api/shares/${s.id}/stats`)).data }
async function revoke(s: any) { await api.delete(`/api/shares/${s.id}`); reloadShares() }

onMounted(async () => { await ensureFileToken(); await loadFolders(); await load() })
</script>
<style scoped>
.lib{display:flex;gap:16px;padding:16px}.left{width:260px;flex-shrink:0}.right{flex:1}.row{display:flex;justify-content:space-between;align-items:center}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.fn{font-weight:600;margin-top:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.meta{color:#888;font-size:12px}.ops{display:flex;gap:6px;margin-top:6px;flex-wrap:wrap}
.hint{color:#888;font-size:12px}.share-row{display:flex;gap:8px;align-items:center;margin:6px 0;flex-wrap:wrap}
</style>
