<template>
  <div class="lib">
    <div class="left">
      <h2>素材管理</h2>
      <div class="row"><h3>文件夹</h3><el-button size="small" @click="openFolderDialog('')">新建</el-button></div>
      <!-- 资源管理器式文件夹树：图标 + 三角 + 计数 + 右键菜单，支持直接投放文件 -->
      <div class="explorer">
        <div class="exp-row" :class="{active: !folderFilter, 'drop-hl': dropTarget==='__all__'}" @click="folderFilter='';load()" title="全部文件（可直接拖入文件上传到默认库）"
             @dragover.prevent="dropTarget='__all__'" @dragleave="dropTarget=''" @drop.prevent="(e) => onDropTo(e, '')">
          <span class="exp-caret"></span>
          <el-icon class="exp-folder exp-all-icon"><Files /></el-icon>
          <span class="exp-name">全部文件</span>
        </div>
        <div v-for="n in flatFolders" :key="n.id" class="exp-row" :class="{active: folderFilter===n.id, 'drop-hl': dropTarget===n.id}"
             :style="{paddingLeft: (8 + n.depth*18)+'px'}"
             @click="selectFolder(n)" @contextmenu.prevent="openMenu($event, n)" :title="`右键：新建 / 重命名 / 删除；拖入文件上传到「${n.path}」`"
             @dragover.prevent="dropTarget=n.id" @dragleave="dropTarget=''" @drop.prevent="(e) => onDropTo(e, n.id)">
          <span class="exp-caret" @click.stop="toggleExpand(n)">
            <el-icon v-if="n.hasChildren"><CaretBottom v-if="!collapsed.has(n.id)" /><CaretRight v-else /></el-icon>
          </span>
          <el-icon class="exp-folder"><FolderOpened v-if="!collapsed.has(n.id)||folderFilter===n.id" /><Folder v-else /></el-icon>
          <span class="exp-name">{{ n.name }}</span>
          <span class="exp-count" v-if="n.subtree_count">{{ n.subtree_count }}</span>
        </div>
      </div>
      <div v-if="menu.show" class="ctx-mask" @click="menu.show=false" @contextmenu.prevent="menu.show=false"></div>
      <div v-if="menu.show" class="ctx-menu" :style="{left: menu.x+'px', top: menu.y+'px'}">
        <div @click="menuNew"><el-icon><Plus /></el-icon> 新建子文件夹</div>
        <div @click="menuRename"><el-icon><Edit /></el-icon> 重命名</div>
        <div class="danger" @click="menuDelete"><el-icon><Delete /></el-icon> 删除</div>
      </div>
      <div class="row" style="margin-top:12px"><h3>上传</h3></div>
      <input ref="fileInput" type="file" multiple accept="image/*,.avif,.heic,.heif" style="display:none" @change="onPick" />
      <input ref="dirInput" type="file" webkitdirectory style="display:none" @change="onPickDir" />
      <el-button size="small" @click="fileInput?.click()">上传文件</el-button>
      <el-button size="small" @click="dirInput?.click()">按文件夹上传</el-button>
      <el-input v-model="uploadTags" placeholder="标签，逗号分隔" style="margin-top:8px" />
      <p class="hint">拖放文件 / 文件夹到右侧，直接上传到当前选中的文件夹{{ selectedFolderName ? `「${selectedFolderName}」` : '（未选则进入「上传素材」库）' }}；也可拖到左侧某个文件夹上精准投放。按文件夹上传会按相对路径自动建树。支持 AVIF/HEIC，旧浏览器由服务端自动转 JPEG 兜底。</p>
    </div>
    <div class="right" @dragover.prevent="onDragOver" @dragleave="onDragLeave" @drop.prevent="onDropPanel">
      <div v-if="dragActive" class="drop-mask">
        <div class="drop-mask-inner">
          <div class="drop-mask-title">松开以上传 {{ dropFilesHint }}</div>
          <div class="drop-mask-sub">目标：{{ selectedFolderName ? `「${selectedFolderName}」` : '「上传素材」库（未选中文件夹）' }}</div>
        </div>
      </div>
      <div class="filters">
        <el-input v-model="q" placeholder="文件名搜索" clearable style="width:180px" @change="load" />
        <el-input v-model="tags" placeholder="标签 a,b" clearable style="width:180px" @change="load" />
        <el-select v-model="match" style="width:110px" @change="load"><el-option label="标签AND" value="all" /><el-option label="标签OR" value="any" /></el-select>
        <el-input v-model="make" placeholder="EXIF: Canon/Sony…" clearable style="width:180px" @change="load" />
        <el-input-number v-model="isoMin" placeholder="ISO min" controls-position="right" style="width:130px" @change="load" />
        <el-input v-model="uploader" placeholder="上传者" clearable style="width:130px" @change="load" />
        <el-select v-model="sort" style="width:120px" @change="load">
          <el-option label="最新优先" value="newest" />
          <el-option label="最早优先" value="oldest" />
          <el-option label="按名称" value="name" />
        </el-select>
        <el-button @click="load">筛选</el-button>
      </div>
      <div class="grid">
        <el-card v-for="a in assets" :key="a.id" class="card">
          <el-image :src="srcOf(a,'thumb_url')" fit="cover" style="width:100%;height:160px" :preview-src-list="[srcOf(a,'file_url')]" title="缩略图，点击加载原图" @error="onImgError(a)" />
          <span v-if="a.is_pinned" class="pin-badge" title="置顶素材，任何排序下保持最前">置顶</span>
          <div class="fn">{{ a.filename }}</div>
          <div class="meta">{{ a.width }}×{{ a.height }} · {{ a.owner }} · {{ (a.exif.Make||'')+' '+(a.exif.Model||'') }}</div>
          <div class="tags"><el-tag v-for="t in a.tags" :key="t" size="small" style="margin:2px">{{ t }}</el-tag></div>
          <div class="ops">
            <el-tooltip content="移动到文件夹" placement="top">
              <el-button circle size="small" @click="openMove(a)"><el-icon><Rank /></el-icon></el-button>
            </el-tooltip>
            <el-tooltip content="编辑标签" placement="top">
              <el-button circle size="small" @click="openTag(a)"><el-icon><PriceTag /></el-icon></el-button>
            </el-tooltip>
            <el-tooltip content="公开链接（图床分享）" placement="top">
              <el-button circle size="small" @click="makeShare(a)"><el-icon><Share /></el-icon></el-button>
            </el-tooltip>
            <el-tooltip :content="a.is_pinned ? '取消置顶' : '置顶（任何排序下保持最前）'" placement="top">
              <el-button circle size="small" :type="a.is_pinned ? 'warning' : ''" @click="togglePin(a)"><el-icon><Top /></el-icon></el-button>
            </el-tooltip>
            <el-tooltip content="删除" placement="top">
              <el-button circle size="small" type="danger" @click="remove(a)"><el-icon><Delete /></el-icon></el-button>
            </el-tooltip>
          </div>
          <div v-if="a.mime==='image/avif'" class="hint">AVIF：Firefox 等旧端访问自动返回 JPEG（<a :href="compatUrl(a)" target="_blank">预览兜底</a>）</div>
        </el-card>
      </div>
    </div>
    <el-dialog v-model="folderDialog.open" title="新建文件夹" width="380px">
      <el-form label-width="52px">
        <el-form-item label="名称"><el-input v-model="folderDialog.name" placeholder="文件夹名" @keyup.enter="createFolder" /></el-form-item>
        <el-form-item label="位置">
          <FolderTreePick v-model="folderDialog.parent" :folders="folders" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="folderDialog.open=false">取消</el-button>
        <el-button type="primary" @click="createFolder">创建</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="tagOpen" title="编辑标签" width="380px">
      <el-input v-model="editTags" placeholder="标签，逗号分隔" @keyup.enter="saveTags" />
      <template #footer>
        <el-button @click="tagOpen=false">取消</el-button>
        <el-button type="primary" @click="saveTags">保存</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="moveOpen" title="移动到文件夹" width="380px">
      <FolderTreePick v-model="editFolder" :folders="folders" />
      <template #footer>
        <el-button @click="moveOpen=false">取消</el-button>
        <el-button type="primary" @click="saveMove">移动</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="shareOpen" title="图床公开链接" width="520px">
      <p>可在任意网页 <code>&lt;img src="URL"&gt;</code> 引用。访问统计默认展开，可随时撤销。</p>
      <el-button size="small" @click="createShare">生成新链接</el-button>
      <div v-for="s in shares" :key="s.id" class="share-block">
        <div class="share-row">
          <code>{{ shareUrl(s) }}</code>
          <el-button size="small" type="danger" @click="revoke(s)" :disabled="s.revoked">撤销</el-button>
        </div>
        <div class="share-stats" v-if="s.stats">
          <div>累计访问 {{ s.stats.view_count }} 次 {{ s.revoked ? '（已撤销）' : '' }}</div>
          <div v-for="(c,ip) in s.stats.by_ip" :key="ip">{{ ip }}：{{ c }} 次</div>
          <div v-for="v in (s.stats.recent||[]).slice(0,5)" :key="v.at+v.ip" class="stat-recent">{{ v.at }} · {{ v.ip }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CaretBottom, CaretRight, Delete, Edit, Files, Folder, FolderOpened, Plus, PriceTag, Rank, Share, Top } from '@element-plus/icons-vue'
import FolderTreePick from '../components/FolderTreePick.vue'
import { api, getFileToken } from '../api/client'

const folders = ref<any[]>([])
const assets = ref<any[]>([])
const folderFilter = ref('')
const q = ref(''), tags = ref(''), match = ref('all'), make = ref(''), uploader = ref('')
const sort = ref('newest')
const isoMin = ref<number | undefined>(undefined)
const uploadTags = ref('')
const fileInput = ref<HTMLInputElement|null>(null)
const dirInput = ref<HTMLInputElement|null>(null)
const editTags = ref('')
const editFolder = ref('')
const editing = ref<any>(null)
const tagOpen = ref(false)
const moveOpen = ref(false)
const shareOpen = ref(false), shares = ref<any[]>([]), sharing = ref<any>(null)
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

// 资源管理器式扁平树（collapsed 为空 = 默认全部展开）
const collapsed = ref<Set<string>>(new Set())
const flatFolders = computed(() => {
  const byParent = new Map<string, any[]>()
  for (const f of folders.value) {
    const k = f.parent_id || ''
    if (!byParent.has(k)) byParent.set(k, [])
    byParent.get(k)!.push(f)
  }
  const out: any[] = []
  const walk = (pid: string, depth: number) => {
    for (const f of byParent.get(pid) || []) {
      const kids = byParent.get(f.id) || []
      out.push({ ...f, depth, hasChildren: kids.length > 0 })
      if (kids.length && !collapsed.value.has(f.id)) walk(f.id, depth + 1)
    }
  }
  walk('', 0)
  return out
})
function toggleExpand(n: any) {
  if (collapsed.value.has(n.id)) collapsed.value.delete(n.id)
  else collapsed.value.add(n.id)
}
function selectFolder(n: any) { folderFilter.value = n.id; load() }
// 右键菜单
const menu = ref({ show: false, x: 0, y: 0, folder: null as any })
function openMenu(e: MouseEvent, n: any) {
  folderFilter.value = n.id; load()
  menu.value = { show: true, x: Math.min(e.clientX, innerWidth - 190), y: Math.min(e.clientY, innerHeight - 150), folder: n }
}

async function loadFolders() { folders.value = (await api.get('/api/assets/folders')).data }
// 新建文件夹弹窗（parent 可预选为右键/当前文件夹）
const folderDialog = ref({ open: false, name: '', parent: '' })
function openFolderDialog(parent = '') {
  folderDialog.value = { open: true, name: '', parent }
}
async function createFolder() {
  const name = folderDialog.value.name.trim()
  if (!name) { ElMessage.warning('请输入文件夹名'); return }
  try {
    await api.post('/api/assets/folders', { name, parent_id: folderDialog.value.parent || null })
    folderDialog.value.open = false
    ElMessage.success('已创建')
    await loadFolders()
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '创建失败') }
}
function menuNew() {
  menu.value.show = false
  openFolderDialog(menu.value.folder?.id || '')
}
async function menuRename() {
  const n = menu.value.folder
  menu.value.show = false
  if (!n) return
  try {
    const { value } = await ElMessageBox.prompt('重命名文件夹', '重命名', { inputValue: n.name })
    if (!value || !value.trim() || value.trim() === n.name) return
    await api.patch(`/api/assets/folders/${n.id}`, { name: value.trim() })
    ElMessage.success('已重命名')
    await loadFolders()
  } catch (e: any) {
    if (e?.response) ElMessage.error(e.response.data?.detail || '重命名失败')
  }
}
async function menuDelete() {
  const n = menu.value.folder
  menu.value.show = false
  if (!n) return
  try {
    await ElMessageBox.confirm(
      `删除文件夹「${n.path}」${n.subtree_count ? `（含 ${n.subtree_count} 个素材，素材将移入「上传素材」库）` : ''}？`, '删除文件夹',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch { return }
  try {
    await api.delete(`/api/assets/folders/${n.id}`)
    ElMessage.success('已删除')
    await loadFolders()
    // 若当前筛选的文件夹被删（含后代），回到全部文件
    if (folderFilter.value && !folders.value.some((f: any) => f.id === folderFilter.value)) folderFilter.value = ''
    load()
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '删除失败') }
}
async function load() {
  const p: any = {}
  if (folderFilter.value) p.folder_id = folderFilter.value
  if (q.value) p.q = q.value
  if (tags.value) { p.tags = tags.value; p.match = match.value }
  if (make.value) p.make = make.value
  if (isoMin.value) p.iso_min = isoMin.value
  if (uploader.value) p.uploader = uploader.value
  p.sort = sort.value
  assets.value = (await api.get('/api/assets', { params: p })).data
}
async function togglePin(a: any) {
  try {
    if (a.is_pinned) await api.delete(`/api/assets/${a.id}/pin`)
    else await api.post(`/api/assets/${a.id}/pin`)
    ElMessage.success(a.is_pinned ? '已取消置顶' : '已置顶')
    await load()
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '操作失败') }
}
interface DropEntry { file: File; rel: string }
// 拖放状态：右侧面板遮罩 + 文件夹行精准投放高亮
const dragActive = ref(false)
const dropTarget = ref('')
const dropFilesHint = ref('')
const selectedFolderName = computed(() => folders.value.find((f: any) => f.id === folderFilter.value)?.path || '')
function onDragOver(e: DragEvent) {
  if (!e.dataTransfer?.types.includes('Files')) return
  dragActive.value = true
  dropTarget.value = ''
  const n = e.dataTransfer.items?.length ?? 0
  dropFilesHint.value = n ? `${n} 个项目` : '文件'
}
function onDragLeave(e: DragEvent) {
  const t = e.currentTarget as HTMLElement | null
  if (t && e.relatedTarget instanceof Node && t.contains(e.relatedTarget)) return
  dragActive.value = false
}
/** 解析拖入内容：文件直取，目录递归展开并保留相对路径（用于自动建树） */
async function collectDropEntries(dt: DataTransfer): Promise<DropEntry[]> {
  const out: DropEntry[] = []
  const items = Array.from(dt.items || [])
  const tops = items.map((it) => (it as any).webkitGetAsEntry?.()).filter(Boolean)
  if (!tops.length) {
    return Array.from(dt.files || []).map((f) => ({ file: f, rel: '' }))
  }
  const walk = (entry: any, prefix: string): Promise<void> => new Promise((resolve) => {
    if (entry.isFile) {
      try {
        entry.file(
          (f: File) => { out.push({ file: f, rel: prefix + f.name }); resolve() },
          () => resolve(),
        )
      } catch { resolve() }
    } else if (entry.isDirectory) {
      const reader = entry.createReader()
      const readBatch = () => {
        reader.readEntries(async (ents: any[]) => {
          if (!ents.length) { resolve(); return }
          for (const en of ents) await walk(en, prefix + entry.name + '/')
          readBatch()
        }, () => resolve())
      }
      readBatch()
    } else resolve()
  })
  for (const t of tops) await walk(t, '')
  return out.slice(0, 500)
}
async function doUploadEntries(entries: DropEntry[], folderId: string) {
  if (!entries.length) {
    ElMessage.warning('没有可上传的文件')
    return
  }
  const fd = new FormData()
  entries.forEach((en) => fd.append('files', en.file, en.file.name))
  fd.append('relpaths', JSON.stringify(entries.map((en) => en.rel)))
  if (folderId) fd.append('folder_id', folderId)
  if (uploadTags.value) fd.append('tags', uploadTags.value)
  const targetName = folders.value.find((f: any) => f.id === folderId)?.path || '「上传素材」库'
  try {
    const r = await api.post('/api/assets/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    const saved = r.data.assets ?? []
    const skipped = r.data.skipped ?? []
    if (skipped.length) {
      ElMessage.warning(`已上传 ${saved.length} 张到${targetName}，跳过 ${skipped.length} 个：${skipped.map((s: any) => s.filename).slice(0, 5).join('、')}${skipped.length > 5 ? '…' : ''}`)
    } else {
      ElMessage.success(`已上传 ${saved.length} 张到${targetName}`)
    }
    await loadFolders(); load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || e.message || '上传失败')
  }
}
async function onDropPanel(e: DragEvent) {
  dragActive.value = false
  dropTarget.value = ''
  if (!e.dataTransfer) return
  await doUploadEntries(await collectDropEntries(e.dataTransfer), folderFilter.value)
}
async function onDropTo(e: DragEvent, fid: string) {
  e.stopPropagation()
  dragActive.value = false
  dropTarget.value = ''
  if (!e.dataTransfer) return
  await doUploadEntries(await collectDropEntries(e.dataTransfer), fid)
}
function onPick(e: Event) {
  const el = e.target as HTMLInputElement
  if (el.files?.length) void doUploadEntries(Array.from(el.files).map((f) => ({ file: f, rel: '' })), folderFilter.value)
  el.value = ''
}
function onPickDir(e: Event) {
  const el = e.target as HTMLInputElement
  if (!el.files?.length) return
  // 保留 webkitRelativePath，后端在当前选中文件夹下按子树建文件夹
  void doUploadEntries(
    Array.from(el.files).map((f) => ({ file: f, rel: (f as any).webkitRelativePath || '' })),
    folderFilter.value,
  )
  el.value = ''
}
function openTag(a: any) { editing.value = a; editTags.value = a.tags.join(','); tagOpen.value = true }
async function saveTags() {
  await api.patch(`/api/assets/${editing.value.id}`, { tags: editTags.value.split(',').map((s) => s.trim()).filter(Boolean) })
  tagOpen.value = false; load()
}
function openMove(a: any) { editing.value = a; editFolder.value = a.folder_id || ''; moveOpen.value = true }
async function saveMove() {
  await api.patch(`/api/assets/${editing.value.id}`, { folder_id: editFolder.value || null })
  moveOpen.value = false; load()
}
async function remove(a: any) {
  await ElMessageBox.confirm(`删除 ${a.filename}？`, '确认', { type: 'warning' })
  await api.delete(`/api/assets/${a.id}`); load()
}
async function makeShare(a: any) { sharing.value = a; shareOpen.value = true; await reloadShares() }
async function reloadShares() {
  const list = (await api.get('/api/shares')).data.filter((s: any) => s.asset_id === sharing.value.id)
  shares.value = list
  // 统计默认展开：逐个拉取后直接挂在链接上展示
  for (const s of shares.value) {
    try { s.stats = (await api.get(`/api/shares/${s.id}/stats`)).data } catch { s.stats = null }
  }
}
async function createShare() { await api.post(`/api/assets/${sharing.value.id}/shares`, {}); reloadShares() }
function shareUrl(s: any) { return `${location.origin}${s.url}` }
async function revoke(s: any) { await api.delete(`/api/shares/${s.id}`); reloadShares() }

function preventNav(e: Event) { e.preventDefault() }
onMounted(async () => {
  await ensureFileToken(); await loadFolders(); await load()
  // 拖到页面空白处也不允许浏览器直接打开文件
  window.addEventListener('dragover', preventNav)
  window.addEventListener('drop', preventNav)
})
onUnmounted(() => {
  window.removeEventListener('dragover', preventNav)
  window.removeEventListener('drop', preventNav)
})
</script>
<style scoped>
.lib{display:flex;gap:16px;padding:16px}.left{width:260px;flex-shrink:0}.right{flex:1;position:relative;min-height:60vh}.row{display:flex;justify-content:space-between;align-items:center}
.exp-row.drop-hl{background:var(--gloss),var(--ios-blue)!important;border-color:var(--ios-blue-border)!important;color:#fff!important}
.exp-row.drop-hl .exp-caret,.exp-row.drop-hl .exp-count{color:#fff!important}
.exp-row.drop-hl .exp-folder{color:#ffe082!important}
.drop-mask{position:absolute;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;border-radius:12px;
  background:rgba(10,12,14,.72);border:2px dashed rgba(124,192,247,.8);pointer-events:none}
.drop-mask-inner{text-align:center}
.drop-mask-title{font-size:20px;font-weight:800;color:#fff;text-shadow:0 -1px 0 rgba(0,0,0,.8)}
.drop-mask-sub{margin-top:8px;font-size:13px;color:#7cc0f7}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.fn{font-weight:600;margin-top:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.meta{color:#888;font-size:12px}.ops{display:flex;gap:6px;margin-top:6px;flex-wrap:wrap}
.card{position:relative}
.pin-badge{position:absolute;top:10px;left:10px;z-index:2;background:linear-gradient(to bottom,#f6c453,#d9930d);color:#3a2703;
  border-radius:4px;padding:2px 8px;font-size:12px;font-weight:800;box-shadow:0 2px 5px rgba(0,0,0,.55)}
.hint{color:#888;font-size:12px}.share-row{display:flex;gap:8px;align-items:center;margin:6px 0;flex-wrap:wrap}
.share-block{margin:10px 0;padding:8px 10px;border-radius:8px;background:rgba(0,0,0,.28);border:1px solid rgba(0,0,0,.5)}
.share-block .share-row{margin:0 0 6px}
.share-block code{flex:1;word-break:break-all;font-size:12px}
.share-stats{font-size:12px;color:#b9b2a0;line-height:1.7}
.share-stats .stat-recent{color:#8f8875;font-size:11px}
</style>
