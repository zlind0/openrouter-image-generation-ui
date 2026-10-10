<template>
  <div class="gen-wrap">
  <div class="side" :class="{open: sideOpen}">
    <div class="side-head">
      <span>{{ sideTab === 'hist' ? '历史记录' : '素材库' }}</span>
      <el-button circle size="small" @click="sideOpen = false">×</el-button>
    </div>
    <div class="seg">
      <button :class="{active: sideTab === 'hist'}" @click="sideTab = 'hist'">历史记录</button>
      <button :class="{active: sideTab === 'lib'}" @click="sideTab = 'lib'">素材库</button>
    </div>
    <div v-show="sideTab === 'hist'">
        <div class="h-title">
          <h2>历史（{{ history.length }}，点击还原）</h2>
          <el-button v-if="history.length" size="small" type="danger" @click="clearHistory">清空</el-button>
        </div>
        <el-empty v-if="!history.length" description="暂无生成记录" />
        <el-card v-for="h in history" :key="h.id" class="history-item" shadow="hover" @click="restoreHistory(h)">
          <template #header>
            <div class="h-head">
              <div class="kv">{{ h.time ? new Date(h.time).toLocaleString() : '' }} · {{ h.model }}</div>
              <el-button size="small" type="danger" circle @click.stop="deleteHistory(h.id)">×</el-button>
            </div>
          </template>
          <div class="p">{{ h.prompt }} <el-tag v-if="!h.error && !(h.images && h.images.length)" type="info" size="small">草稿快照</el-tag></div>
          <el-alert v-if="h.error" :title="h.error" type="error" show-icon :closable="false" />
          <div v-else class="result-grid">
            <div v-for="(t, i) in h.thumbs" :key="i" class="result-item">
              <el-image :src="authUrl(t)" fit="cover" class="zoomable" @click.stop="openHistViewer(h, i)" />
            </div>
          </div>
          <div v-if="h.usage" class="cost">cost: {{ h.usage.cost ?? '—' }} · tokens: {{ h.usage.total_tokens }}</div>
        </el-card>
    </div>
    <div v-show="sideTab === 'lib'">
        <div class="row" style="display:flex;gap:8px;margin-bottom:8px">
          <el-select v-model="libFolder" clearable placeholder="全部文件" style="flex:1" @change="loadLibAssets">
            <el-option v-for="f in folders" :key="f.id" :label="f.path" :value="f.id" />
          </el-select>
          <el-input v-model="libQ" placeholder="文件名搜索" clearable style="flex:1" @change="loadLibAssets" />
        </div>
        <div class="pick-grid">
          <div v-for="a in libAssets" :key="a.id" class="pick-item" :class="{sel: libRefIds.has(a.id)}" @click="toggleLibRef(a)" :title="a.filename">
            <el-image :src="authUrl(a.thumb_url)" fit="cover" />
            <span v-if="libRefIds.has(a.id)" class="pick-check">✓</span>
            <span v-if="a.is_pinned" class="pick-pin" title="置顶素材">顶</span>
            <div class="pick-name">{{ a.filename }}</div>
          </div>
        </div>
        <el-empty v-if="!libAssets.length" description="该目录暂无素材" />
        <div class="hint">点击图片加入 / 移除参考图（已选 {{ references.length }} 张）</div>
    </div>
  </div>
  <div class="side-mask" v-if="sideOpen" @click="sideOpen = false"></div>
  <div class="gen">
    <div class="gen-head">
      <h2>图片生成</h2>
      <div class="narrow-btns">
        <el-button size="small" @click="openSide('hist')">历史记录</el-button>
        <el-button size="small" @click="openSide('lib')">素材库</el-button>
      </div>
    </div>
    <div class="topbar">
      <el-select v-model="selectedId" filterable placeholder="选择模型" style="width:320px" :loading="loadingModels" @change="selectModel">
        <el-option v-for="m in models" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-button @click="refreshModels" :loading="loadingModels">刷新模型</el-button>
      <span class="balance">{{ balanceText }}</span>
      <el-button size="small" @click="refreshBalance" :loading="loadingBalance">刷新余额</el-button>
    </div>
    <div class="field"><label>Prompt *</label>
      <el-input v-model="prompt" type="textarea" :rows="5" placeholder="描述你想要的画面…" />
    </div>
    <div v-if="endpoints.length" class="field"><label>Provider</label>
      <el-select v-model="providerChoice" clearable placeholder="自动路由" style="width:100%">
        <el-option label="自动路由（默认）" value="" />
        <el-option v-for="e in endpoints" :key="e.provider_slug" :label="`${e.provider_name} (${e.provider_slug})`" :value="e.provider_slug" />
      </el-select>
    </div>
    <div v-for="f in paramFields" :key="f.key" class="field">
      <label>{{ f.label }} <span class="kv">{{ f.key }}</span></label>
      <el-select v-if="f.kind==='enum'" v-model="paramValues[f.key]" clearable placeholder="不发送" style="width:100%">
        <el-option v-for="v in f.values" :key="v" :label="v" :value="v" />
      </el-select>
      <el-slider v-else-if="f.kind==='range'" v-model="paramValues[f.key]" :min="f.min??0" :max="f.max??10" :step="1" show-input :show-input-controls="false" />
      <el-input-number v-else-if="f.kind==='number'" v-model="paramValues[f.key]" controls-position="right" style="width:100%" />
      <el-input v-else-if="f.kind==='text'" v-model="paramValues[f.key]" placeholder="留空不发送" clearable />
      <div v-else-if="f.kind==='boolean'"><el-switch v-model="paramValues[f.key]" /></div>
    </div>
    <div class="field"><label>参考图（可选，上传即自动存入素材库）</label>
      <div class="row" style="margin-bottom:8px">
        <el-button @click="pickFiles">选择文件</el-button>
        <el-button @click="sideTab='lib'">从素材库选择</el-button>
        <el-input v-model="imageUrl" placeholder="或粘贴图片 URL 后点添加（自动入库）" style="flex:1">
          <template #append><el-button @click="addUrl">添加</el-button></template>
        </el-input>
      </div>
      <div class="refs"><div v-for="(r,i) in references" :key="i" class="ref" :title="r.name + (r.assetId ? '（已入库）' : '（未入库）')">
        <el-image :src="refSrc(r)" fit="cover" class="zoomable" @click="openRefViewer(i)" />
        <el-button class="ref-del" size="small" circle type="danger" @click="references.splice(i,1)">×</el-button>
      </div></div>
    </div>
    <div style="display:flex;gap:8px;align-items:center;margin-top:4px">
      <el-button type="primary" :loading="generating" :disabled="!canGenerate" @click="generate">{{ generating ? `生成中… ${elapsed}s` : '生成图片' }}</el-button>
      <el-button v-if="generating" size="small" @click="cancelGenerate">取消</el-button>
    </div>
    <div v-if="genStages.length" class="stages">
      <el-steps :active="stageActive" finish-status="success" process-status="process" direction="vertical">
        <el-step v-for="s in genStages" :key="s.key" :title="s.label" :status="s.status" :description="s.detail" />
      </el-steps>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" style="margin-top:8px" />
    <div v-if="usageText" style="margin-top:8px">{{ usageText }}</div>
    <div v-if="currentImages.length" class="result-grid" style="margin-top:12px">
      <div v-for="(img,i) in currentImages" :key="i" class="result-item">
        <el-image :src="imgDisplayUrl(img)" fit="cover" class="zoomable" @click="openResultViewer(i)" />
        <div style="display:flex;gap:6px;margin-top:6px">
          <el-button size="small" @click="saveImage(img,i)">下载</el-button>
          <el-button size="small" type="primary" @click="openStock(img)">入库</el-button>
        </div>
      </div>
    </div>
    <el-dialog v-model="stockOpen" title="存入素材库" width="420px">
      <el-form label-width="70px">
        <el-form-item label="文件夹">
          <el-select v-model="stockFolder" placeholder="选择文件夹" style="width:100%">
            <el-option v-for="f in folders" :key="f.id" :label="f.path" :value="f.id" />
          </el-select>
          <div class="hint">默认进入「生成图片」库（生成成功会自动推送到该目录）</div>
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="stockTags" placeholder="标签，逗号分隔" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="stockOpen=false">取消</el-button>
        <el-button type="primary" :loading="stocking" @click="confirmStock">确认入库</el-button>
      </template>
    </el-dialog>
    <!-- 统一全屏预览：teleport 到 body，不受 96px 小格/抽屉层级约束 -->
    <teleport to="body">
      <el-image-viewer v-if="refViewerShow" :url-list="refsPreview" :initial-index="refViewerIndex" :z-index="9999" infinite hide-on-click-modal @close="refViewerShow = false" />
    </teleport>
    <teleport to="body">
      <el-image-viewer v-if="histViewerShow" :key="histViewerKey" :url-list="histViewerList" :initial-index="histViewerIndex" :z-index="9999" infinite hide-on-click-modal @close="histViewerShow = false" />
    </teleport>
    <teleport to="body">
      <el-image-viewer v-if="resultViewerShow" :url-list="resultPreviewList" :initial-index="resultViewerIndex" :z-index="9999" infinite hide-on-click-modal @close="resultViewerShow = false" />
    </teleport>
  </div>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, getFileToken, orApi } from '../api/client'
import { pickImages, saveImage as dl } from '../api/native'
import { buildParamFields, cleanParams, type ParamField } from '../api/params'

interface RefItem { kind: 'upload' | 'library' | 'url'; assetId: string | null; dataUrl: string; name: string; thumbUrl?: string }
interface GenImg { b64_json?: string; media_type?: string; url?: string }
interface GenStage { key: string; label: string; status: 'wait' | 'process' | 'finish' | 'error'; detail?: string }

const models = ref<any[]>([])
const endpoints = ref<any[]>([])
const selectedId = ref('')
const prompt = ref('')
const paramFields = ref<ParamField[]>([])
const paramValues = ref<Record<string, any>>({})
const providerChoice = ref('')
const references = ref<RefItem[]>([])
const imageUrl = ref('')
const loadingModels = ref(false)
const loadingBalance = ref(false)
const generating = ref(false)
const error = ref('')
const balanceText = ref('')
const usageText = ref('')
const genStages = ref<GenStage[]>([])
const elapsed = ref(0)
let elapsedTimer: any = null
let genAbort: AbortController | null = null
const stageActive = computed(() => {
  const i = genStages.value.findIndex((s) => s.status === 'process' || s.status === 'error')
  if (i >= 0) return i
  const done = genStages.value.filter((s) => s.status === 'finish').length
  return done
})
function resetStages() {
  genStages.value = [
    { key: 'sent', label: '请求已发出', status: 'wait' },
    { key: 'received', label: '服务器已收到请求', status: 'wait' },
    { key: 'forwarding', label: '请求发送中：转发给 OpenRouter', status: 'wait' },
    { key: 'generating', label: 'OpenRouter 生成中', status: 'wait' },
    { key: 'downloading', label: '图片回传 / 下载中', status: 'wait' },
    { key: 'saving', label: '历史 + 素材库保存中', status: 'wait' },
  ]
  elapsed.value = 0
}
function setStage(key: string, status: GenStage['status'], detail = '') {
  const s = genStages.value.find((x) => x.key === key)
  if (!s) return
  s.status = status
  if (detail) s.detail = detail
  // 前序阶段自动标 finish，保证步骤条连续
  const order = ['sent', 'received', 'forwarding', 'generating', 'downloading', 'saving']
  const idx = order.indexOf(key)
  if (status === 'process' || status === 'finish') {
    for (let i = 0; i < idx; i++) {
      const p = genStages.value.find((x) => x.key === order[i])
      if (p && p.status === 'wait') p.status = 'finish'
    }
  }
  if (status === 'error') {
    for (const x of genStages.value) if (x.status === 'process') x.status = 'error'
  }
}
function startElapsed() {
  stopElapsed()
  elapsedTimer = setInterval(() => { elapsed.value++ }, 1000)
}
function stopElapsed() {
  if (elapsedTimer) clearInterval(elapsedTimer)
  elapsedTimer = null
}
/** 图片已在客户端显示出来后，步骤条全部消失（成功才清，失败保留定位） */
async function hideStagesOnShown() {
  if (!currentImages.value.length) return
  await nextTick()
  genStages.value = []
}
function cancelGenerate() {
  try { genAbort?.abort() } catch {}
  error.value = '已取消本次生成'
  setStage('generating', 'error', '用户取消')
  generating.value = false
  stopElapsed()
}
const currentImages = ref<GenImg[]>([])
const folders = ref<any[]>([])
// 生成结果自动入库到「生成图片」；弹窗手动入库默认也预选该目录
const stockOpen = ref(false)
const stocking = ref(false)
const stockImg = ref<GenImg|null>(null)
const stockFolder = ref('')
const stockTags = ref('')
const GEN_FOLDER_NAME = '生成图片'
function findGenFolderId(): string {
  const hit = folders.value.find((f: any) => f.path === GEN_FOLDER_NAME || f.name === GEN_FOLDER_NAME)
  return hit ? hit.id : ''
}
/** 确保「生成图片」目录存在并返回其 id（不存在则创建） */
async function ensureGenFolderId(): Promise<string> {
  let fid = findGenFolderId()
  if (fid) return fid
  try {
    const r = await api.post('/api/assets/folders', { name: GEN_FOLDER_NAME, parent_id: null })
    fid = r.data?.id || ''
  } catch (e: any) {
    // 并发创建导致“已存在”时重新拉取列表再找一次
    try { folders.value = (await api.get('/api/assets/folders')).data } catch {}
    fid = findGenFolderId()
  }
  if (!fid) {
    try { folders.value = (await api.get('/api/assets/folders')).data } catch {}
    fid = findGenFolderId()
  }
  return fid
}
/** 生成成功后自动推送全部结果图到素材库「生成图片」目录 */
async function autoStockGenerated(images: GenImg[]) {
  if (!images.length) return
  try {
    const fid = await ensureGenFolderId()
    const ts = Date.now()
    let ok = 0
    for (let i = 0; i < images.length; i++) {
      try {
        const { b64, mime } = await imgToB64(images[i])
        const ext = mime.includes('jpeg') || mime.includes('jpg') ? '.jpg' : mime.includes('webp') ? '.webp' : '.png'
        await api.post('/api/assets/from-generation', {
          b64,
          mime,
          filename: `gen-${ts}-${i}${ext}`,
          folder_id: fid || null, // 空则后端默认归入「生成图片」
          tags: [],
          prompt: prompt.value.trim(),
        })
        ok++
      } catch (e) { console.warn('单张自动入库失败', e) }
    }
    if (ok) {
      ElMessage.success(`已自动存入素材库「${GEN_FOLDER_NAME}」（${ok} 张）`)
      try { await loadLibAssets() } catch {}
    } else {
      ElMessage.warning('生成成功，但自动入库素材库失败，可点击「入库」手动重试')
    }
  } catch (e) { console.warn('自动入库失败', e) }
}
// 文件令牌（<img> 鉴权）
const ftoken = ref('')
async function ensureFileToken(force = false) {
  try { ftoken.value = await getFileToken(force) } catch {}
}
function authUrl(u: string): string {
  if (!u) return u
  return ftoken.value ? u + (u.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(ftoken.value) : u
}

/* ---- 工作区草稿：存服务器，防刷新丢失；点历史还原前先快照成新条目防覆盖 ---- */
const dirty = ref(false) // 用户是否改过工作区（生成/还原成功后清零）
let suppressDirty = false
let draftReady = false
function markDirty() {
  if (!suppressDirty && draftReady) dirty.value = true
}
watch([prompt, selectedId, providerChoice], () => markDirty())
watch(paramValues, () => markDirty(), { deep: true })
watch(references, () => markDirty(), { deep: true })

let draftTimer: any = null
function scheduleDraftSave() {
  if (!draftReady) return
  clearTimeout(draftTimer)
  draftTimer = setTimeout(() => void saveDraft(), 800)
}
watch([prompt, selectedId, providerChoice, references], () => scheduleDraftSave(), { deep: true })
watch(paramValues, () => scheduleDraftSave(), { deep: true })

function serializableRefs(): any[] {
  return references.value.map((r) => ({
    kind: r.kind,
    assetId: r.assetId,
    name: r.name,
    thumbUrl: r.thumbUrl || '',
    // data: URL 太大不进草稿（已入库的用 assetId 恢复；http 外链原样保留）
    dataUrl: r.dataUrl.startsWith('data:')
      ? (r.dataUrl.length > 200_000 ? '' : r.dataUrl)
      : r.dataUrl,
  }))
}
async function saveDraft() {
  try {
    await api.put('/api/workspace/draft', {
      generate: {
        model: selectedId.value,
        prompt: prompt.value,
        params: paramValues.value,
        provider_choice: providerChoice.value,
        references: serializableRefs(),
      },
    })
  } catch (e) { console.warn('草稿保存失败', e) }
}
async function applyDraft() {
  let d: any = null
  try { d = (await api.get('/api/workspace/draft')).data?.generate } catch {}
  if (!d) return
  suppressDirty = true
  try {
    if (typeof d.prompt === 'string') prompt.value = d.prompt
    if (Array.isArray(d.references)) {
      references.value = d.references
        .filter((r: any) => r && (r.assetId || r.dataUrl))
        .map((r: any) => ({
          kind: r.assetId ? 'library' as const : (r.dataUrl.startsWith('http') ? 'url' as const : 'upload' as const),
          assetId: r.assetId || null,
          dataUrl: r.dataUrl || '',
          name: r.name || '参考图',
          thumbUrl: r.thumbUrl || '',
        }))
    }
    if (d.model) {
      try { await selectModel(d.model) } catch {}
    }
    if (d.params && typeof d.params === 'object') {
      for (const [k, v] of Object.entries(d.params)) paramValues.value[k] = v
    }
    providerChoice.value = d.provider_choice ?? ''
  } finally {
    await nextTick()
    suppressDirty = false
    dirty.value = false
  }
}
/** 还原前快照：工作区有未保存改动则先存成一条新历史（无图快照），再打开旧记录 */
async function snapshotWorkspace() {
  if (!dirty.value) return
  if (!prompt.value.trim() && !references.value.length) {
    dirty.value = false
    return
  }
  try {
    await api.post('/api/history', {
      model: selectedId.value,
      prompt: prompt.value.trim(),
      params: { ...paramValues.value },
      provider_choice: providerChoice.value || null,
      reference_ids: references.value.map((r) => r.assetId).filter(Boolean),
      images: [],
      usage: null,
      error: null,
    })
    await loadHistory()
    ElMessage.success('当前工作已快照为一条新历史')
  } catch (e) { console.warn('快照保存失败', e) }
}

const canGenerate = computed(() => !!selectedId.value && !!prompt.value.trim() && !generating.value)
const refsPreview = computed(() => references.value.map(refPreviewSrc))

/* ---- 统一全屏预览（参考图 / 历史 / 生成结果） ---- */
const refViewerShow = ref(false)
const refViewerIndex = ref(0)
async function openRefViewer(i: number) {
  await ensureFileToken()
  refViewerIndex.value = i
  refViewerShow.value = true
}
const histViewerShow = ref(false)
const histViewerList = ref<string[]>([])
const histViewerIndex = ref(0)
const histViewerKey = ref(0)
async function openHistViewer(h: any, i: number) {
  await ensureFileToken()
  histViewerList.value = (h.images ?? []).map(authUrl)
  histViewerIndex.value = i
  histViewerKey.value++
  histViewerShow.value = true
}
const resultViewerShow = ref(false)
const resultViewerIndex = ref(0)
const resultPreviewList = computed(() => currentImages.value.map(imgDisplayUrl))
function openResultViewer(i: number) {
  resultViewerIndex.value = i
  resultViewerShow.value = true
}

async function loadModels() {
  // 初始只读服务端缓存（快；超 24h 服务端自动回源）；手动刷新走 refreshModels/refreshBalance
  loadingModels.value = true
  try {
    const list = await orApi.models()
    models.value = Array.isArray(list) ? list : []
    await loadBalance()
    try { folders.value = (await api.get('/api/assets/folders')).data } catch {}
  // 入库默认文件夹：优先「生成图片」，兼容老数据回落「上传素材」
  if (!stockFolder.value) {
    const hit = folders.value.find((f: any) => f.path === '生成图片' || f.name === '生成图片')
      || folders.value.find((f: any) => f.path === '上传素材' || f.name === '上传素材')
    if (hit) stockFolder.value = hit.id
  }
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || e.message) }
  finally { loadingModels.value = false }
}
async function refreshModels() {
  loadingModels.value = true
  try {
    const list = await orApi.refreshModels()
    models.value = Array.isArray(list) ? list : []
    ElMessage.success(`已从上游刷新，共 ${models.value.length} 个模型`)
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || e.message) }
  finally { loadingModels.value = false }
}
function formatBalance(info: any): string {
  return info.limit_remaining != null ? `剩余额度 $${info.limit_remaining.toFixed(2)}` : `已用 $${info.usage?.toFixed?.(2) ?? '?'}`;
}
async function loadBalance() {
  const info = await orApi.keyInfo().catch(() => null)
  if (info) balanceText.value = formatBalance(info)
}
async function refreshBalance() {
  loadingBalance.value = true
  try {
    const info = await orApi.refreshBalance()
    balanceText.value = formatBalance(info)
    ElMessage.success('余额已从上游刷新')
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || e.message) }
  finally { loadingBalance.value = false }
}
async function selectModel(id: string) {
  if (!id) return
  selectedId.value = id; paramFields.value = []; paramValues.value = {}; endpoints.value = []
  const m = models.value.find((x) => x.id === id)
  if (m?.supported_parameters) applyFields(m.supported_parameters)
  try {
    endpoints.value = await orApi.endpoints(id)
    if (endpoints.value[0]) applyFields(endpoints.value[0].supported_parameters)
  } catch {}
}
function applyFields(s: any) {
  if (!s) return
  const fs = buildParamFields(s)
  paramFields.value = fs
  const next = { ...paramValues.value }
  for (const f of fs) if (!(f.key in next)) next[f.key] = f.defaultValue
  paramValues.value = next
}
function imgDisplayUrl(img: GenImg): string {
  if (img.url) return img.url
  const b64 = img.b64_json || ''
  if (b64.startsWith('data:') || b64.startsWith('http')) return b64
  return `data:${img.media_type || 'image/png'};base64,${b64}`
}
async function imgToB64(img: GenImg): Promise<{ b64: string; mime: string }> {
  if (img.b64_json) return { b64: img.b64_json, mime: img.media_type || 'image/png' }
  const res = await fetch(img.url || '')
  const blob = await res.blob()
  const dataUrl: string = await new Promise((res2, rej) => {
    const fr = new FileReader()
    fr.onload = () => res2(String(fr.result))
    fr.onerror = () => rej(new Error('读取图片失败'))
    fr.readAsDataURL(blob)
  })
  return { b64: dataUrl.split(',')[1], mime: blob.type || 'image/png' }
}

/* ---- 参考图：上传即自动入库，也可从库选择 ----
   prompt 下方一律显示缩略图（/thumb），点击预览才看原图 */
function refSrc(r: RefItem): string {
  if (r.dataUrl.startsWith('data:')) return r.dataUrl
  if (r.assetId) return authUrl(`/api/assets/${r.assetId}/thumb`)
  return r.dataUrl
}
function refPreviewSrc(r: RefItem): string {
  if (r.dataUrl.startsWith('data:')) return r.dataUrl
  if (r.assetId) return authUrl(`/api/assets/${r.assetId}/file`)
  return r.dataUrl
}
async function stockRefAsset(blob: Blob, name: string): Promise<string | null> {
  try {
    const fd = new FormData()
    fd.append('files', blob, name)
    const r = await api.post('/api/assets/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    const saved = r.data.assets ?? []
    if (saved.length) {
      ElMessage.success(`已自动存入素材库：${name}`)
      return saved[0].id
    }
    const skipped = r.data.skipped ?? []
    ElMessage.warning(skipped[0]?.reason || '参考图入库被跳过')
    return null
  } catch (e: any) {
    ElMessage.warning(`参考图自动入库失败（仍可用于本次生成）：${e.response?.data?.detail || e.message}`)
    return null
  }
}
function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((res, rej) => {
    const fr = new FileReader()
    fr.onload = () => res(String(fr.result))
    fr.onerror = () => rej(new Error('读取图片失败'))
    fr.readAsDataURL(blob)
  })
}
async function pickFiles() {
  const picked = await pickImages()
  for (const p of picked) {
    try {
      const assetId = await stockRefAsset(p.file, p.name)
      references.value.push({ kind: 'upload', assetId, dataUrl: p.dataUrl, name: p.name })
    } catch (e: any) { ElMessage.error(e.message || '添加参考图失败') }
  }
}
async function addUrl() {
  const u = imageUrl.value.trim(); if (!u) return; imageUrl.value = ''
  try {
    const res = await fetch(u)
    if (!res.ok) throw new Error(`拉图失败 (${res.status})`)
    const blob = await res.blob()
    const name = u.slice(0, 40) || 'url-image'
    const assetId = await stockRefAsset(blob, name)
    references.value.push({ kind: 'upload', assetId, dataUrl: await blobToDataUrl(blob), name })
  } catch (e: any) {
    // 直连拉取失败（如跨域）：保留原 URL 用于本次生成，但无法入库
    ElMessage.warning(`URL 拉取失败，已保留原地址（未入库）：${e.message}`)
    references.value.push({ kind: 'url', assetId: null, dataUrl: u, name: u.slice(0, 40) })
  }
}
/* 左侧栏 tab：历史记录 / 素材库（v-show 切换，DOM 常驻，滚动/搜索/勾选状态保留） */
const sideTab = ref('hist')
/* 窄屏抽屉开关（宽屏无影响） */
const sideOpen = ref(false)
function openSide(tab: 'hist' | 'lib') {
  sideTab.value = tab
  sideOpen.value = true
}
const libFolder = ref('')
const libQ = ref('')
const libAssets = ref<any[]>([])
const libRefIds = computed(() => new Set(references.value.map((r) => r.assetId).filter(Boolean) as string[]))
async function loadLibAssets() {
  const p: any = {}
  if (libFolder.value) p.folder_id = libFolder.value
  if (libQ.value) p.q = libQ.value
  libAssets.value = (await api.get('/api/assets', { params: p })).data
}
/* 素材库点击即加入/移除参考图：只存 assetId + thumb_url，不下载原图 */
function toggleLibRef(a: any) {
  const i = references.value.findIndex((r) => r.assetId === a.id)
  if (i >= 0) references.value.splice(i, 1)
  else references.value.push({ kind: 'library', assetId: a.id, dataUrl: '', thumbUrl: a.thumb_url || '', name: a.filename })
}

async function generate() {
  if (!canGenerate.value) return
  generating.value = true; error.value = ''; usageText.value = ''; currentImages.value = []
  resetStages(); startElapsed()
  genAbort = new AbortController()
  setStage('sent', 'process', `模型 ${selectedId.value} · 参考图 ${references.value.length} 张`)
  const cleaned = cleanParams(paramValues.value)
  const { stream, ...rest } = cleaned as any
  // 库选择的图只发 assetId，由服务端读盘组装；上传/URL 的才由客户端带 dataURL/原地址
  const libIds = references.value.filter((r) => r.kind === 'library' && r.assetId).map((r) => r.assetId as string)
  const clientRefs: any[] = []
  for (const r of references.value) {
    if (r.kind === 'library') continue
    if (!r.dataUrl) continue
    clientRefs.push({ type: 'image_url' as const, image_url: { url: r.dataUrl } })
  }
  const body = {
    model: selectedId.value, prompt: prompt.value.trim(),
    reference_ids: libIds,
    params: { ...rest, input_references: clientRefs.length ? clientRefs : undefined,
      provider: providerChoice.value ? { only: [providerChoice.value] } : undefined },
  }
  const refIds = references.value.map((r) => r.assetId).filter(Boolean) as string[]
  const applyServerStage = (ev: any) => {
    if (!ev || ev.type !== 'stage') return
    const msg = ev.message || ''
    switch (ev.stage) {
      case 'received': setStage('sent', 'finish'); setStage('received', 'finish', msg || '服务器已收到请求'); setStage('forwarding', 'process'); break
      case 'assembling': setStage('sent', 'finish'); setStage('received', 'finish'); setStage('forwarding', 'process', msg); break
      case 'forwarding': setStage('sent', 'finish'); setStage('received', 'finish'); setStage('forwarding', 'process', msg); break
      case 'upstream_connected': setStage('forwarding', 'finish', msg || '已转发给 OpenRouter'); setStage('generating', 'process'); break
      case 'generating': setStage('forwarding', 'finish'); setStage('generating', 'process', msg); break
      case 'downloading': setStage('generating', 'finish'); setStage('downloading', 'process', msg); break
      case 'error': setStage('forwarding', 'error', msg); setStage('generating', 'error', msg); break
    }
  }
  try {
    if (stream) {
      setStage('sent', 'finish'); setStage('received', 'process', '等待服务器确认…')
      const token = localStorage.getItem('access_token')
      const resp = await fetch('/api/openrouter/images/stream', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify(body), credentials: 'include', signal: genAbort.signal })
      if (!resp.ok || !resp.body) throw new Error(`服务器拒绝 (${resp.status})`)
      setStage('received', 'finish', '服务器已收到请求')
      const reader = resp.body.getReader(); const dec = new TextDecoder(); let buf = ''
      let doneUsage: any = undefined
      const handleLine = (t: string) => {
        const p = t.slice(5).trim(); if (!p) return
        if (p === '[DONE]') return
        let ev: any = null
        try { ev = JSON.parse(p) } catch { return }
        if (ev.type === 'stage') { applyServerStage(ev); return }
        if (ev.type === 'image_generation.completed' && ev.b64_json) {
          currentImages.value = [{ b64_json: ev.b64_json, media_type: ev.media_type }]
          if (ev.usage) { doneUsage = ev.usage; usageText.value = `cost: $${ev.usage.cost ?? '?'}` }
          setStage('generating', 'finish'); setStage('downloading', 'finish', '图片已回传')
        } else if (ev.type === 'error') throw new Error(ev.error?.message || '流式失败')
      }
      for (;;) {
        const { done, value } = await reader.read(); if (done) break
        buf += dec.decode(value, { stream: true })
        const lines = buf.split('\n'); buf = lines.pop() ?? ''
        for (const line of lines) { const t = line.trim(); if (!t.startsWith('data:')) continue; handleLine(t) }
      }
      if (buf.trim().startsWith('data:')) { try { handleLine(buf.trim()) } catch (e) { throw e } }
      setStage('downloading', 'finish', '图片已回传')
      setStage('saving', 'process', '正在保存历史 + 自动入库「生成图片」…')
      if (await pushHistory({ images: currentImages.value, usage: doneUsage, refIds, paramsSnapshot: rest })) dirty.value = false
      await autoStockGenerated(currentImages.value)
      setStage('saving', 'finish', '已保存')
      await hideStagesOnShown()
    } else {
      // 非流式无 SSE：本地模拟阶段 + 已耗时，真实进度以服务器返回为准
      setStage('sent', 'finish'); setStage('received', 'finish', '服务器已收到请求（非流式，等待一次性返回）')
      setStage('forwarding', 'process', `服务端组装库参考图 ${libIds.length} 张并转发中…`)
      const res = await api.post('/api/openrouter/images', body, { signal: genAbort.signal }).then((r) => r.data)
      setStage('forwarding', 'finish'); setStage('generating', 'finish', '上游已返回'); setStage('downloading', 'finish', '图片已下载')
      currentImages.value = res.data
      if (res.usage) usageText.value = `cost: $${res.usage.cost ?? '?'}`
      setStage('saving', 'process', '正在保存历史 + 自动入库…')
      if (await pushHistory({ images: res.data, usage: res.usage, refIds, paramsSnapshot: rest })) dirty.value = false
      await autoStockGenerated(res.data)
      setStage('saving', 'finish', '已保存')
      await hideStagesOnShown()
    }
  } catch (e: any) {
    if (e?.name === 'CanceledError' || e?.name === 'AbortError' || /cancel|abort|canceled/i.test(e?.message || '')) {
      error.value = '已取消本次生成'
    } else {
      const msg = e.response?.data?.detail || e.message
      error.value = msg
      ElMessage.error(msg)
    }
    for (const s of genStages.value) if (s.status === 'process' || s.status === 'wait') { s.status = 'error'; break }
    await pushHistory({ images: [], error: error.value, refIds, paramsSnapshot: rest })
  }
  finally { generating.value = false; stopElapsed(); genAbort = null }
}

/* ---- 历史：服务端持久化，点击还原 prompt/参数/参考图 ---- */
const history = ref<any[]>([])
async function loadHistory() {
  try { history.value = (await api.get('/api/history')).data } catch { history.value = [] }
}
async function pushHistory(h: { images: GenImg[]; usage?: any; error?: string; refIds: string[]; paramsSnapshot: any }): Promise<boolean> {
  try {
    const imgs = []
    for (const img of h.images) {
      const { b64, mime } = await imgToB64(img)
      imgs.push({ b64, mime })
    }
    await api.post('/api/history', {
      model: selectedId.value,
      prompt: prompt.value.trim(),
      params: h.paramsSnapshot ?? {},
      provider_choice: providerChoice.value || null,
      reference_ids: h.refIds,
      images: imgs,
      usage: h.usage ?? null,
      error: h.error ?? null,
    })
    await loadHistory()
    return true
  } catch (e) { console.warn('历史保存失败', e); return false }
}
async function restoreHistory(h: any) {
  // 先快照当前工作区（有未保存改动时存成一条新历史），再打开旧记录，避免覆盖丢失
  await snapshotWorkspace()
  suppressDirty = true
  try {
    prompt.value = h.prompt
    references.value = (h.references ?? []).map((r: any) => ({ kind: 'library' as const, assetId: r.id, dataUrl: '', thumbUrl: r.thumb_url || '', name: r.filename }))
    currentImages.value = (h.images ?? []).map((u: string) => ({ url: authUrl(u) }))
    error.value = h.error ?? ''
    usageText.value = h.usage ? `cost: $${h.usage.cost ?? '?'} · tokens: ${h.usage.total_tokens ?? '?'}` : ''
    if (h.model !== selectedId.value) {
      try { await selectModel(h.model) } catch {}
    }
    if (h.params) {
      for (const [k, v] of Object.entries(h.params)) paramValues.value[k] = v
    }
    providerChoice.value = h.providerChoice ?? ''
  } finally {
    await nextTick()
    suppressDirty = false
    dirty.value = false
  }
  ElMessage.success(`已还原：${h.model}`)
  window.scrollTo({ top: 0 })
}
async function deleteHistory(id: string) {
  await api.delete(`/api/history/${id}`)
  await loadHistory()
  ElMessage.success('已删除该条历史')
}
async function clearHistory() {
  try {
    await ElMessageBox.confirm(`确定删除全部 ${history.value.length} 条历史吗？`, '清空历史', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch { return }
  await api.delete('/api/history')
  await loadHistory()
}

async function saveImage(img: GenImg, i: number) {
  if (img.b64_json) {
    await dl({ b64: img.b64_json, mediaType: img.media_type, suggestedName: `or-${Date.now()}-${i}.png` })
    return
  }
  // 历史还原的图片：拉取后下载
  const res = await fetch(img.url || '')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `or-history-${Date.now()}-${i}.png`
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}
async function openStock(img: GenImg) {
  try {
    const { b64, mime } = await imgToB64(img)
    stockImg.value = { b64_json: b64, media_type: mime }
  } catch (e: any) { ElMessage.error(e.message || '读取图片失败'); return }
  stockTags.value = ''
  // 每次打开都把「生成图片」作为预选（若存在），兼容回落「上传素材」
  const hit = folders.value.find((f: any) => f.path === '生成图片' || f.name === '生成图片')
    || folders.value.find((f: any) => f.path === '上传素材' || f.name === '上传素材')
  stockFolder.value = hit ? hit.id : (folders.value[0]?.id || '')
  stockOpen.value = true
}
async function confirmStock() {
  if (!stockImg.value?.b64_json) return
  stocking.value = true
  try {
    await api.post('/api/assets/from-generation', {
      b64: stockImg.value.b64_json,
      mime: stockImg.value.media_type || 'image/png',
      folder_id: stockFolder.value || null, // 空则后端默认归入「生成图片」
      tags: stockTags.value.split(',').map((s) => s.trim()).filter(Boolean),
      prompt: prompt.value.trim(),
    })
    ElMessage.success('已存入素材库')
    stockOpen.value = false
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '入库失败') }
  finally { stocking.value = false }
}
onMounted(async () => {
  await ensureFileToken()
  await loadModels()
  await applyDraft()
  draftReady = true
  await loadHistory()
  await loadLibAssets()
})
</script>
<style scoped>
.gen-wrap{display:grid;grid-template-columns:minmax(300px,1fr) minmax(0,2fr);gap:16px;max-width:1400px;width:100%;margin:0 auto;padding:16px;align-items:start}
.gen{min-width:0;order:2}.side{min-width:0;order:1}
@media (max-width:1100px){.gen-wrap{grid-template-columns:1fr}.gen{order:1}}
.topbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.field{margin:12px 0}.kv{color:#888;font-size:12px}.refs{display:flex;gap:8px;flex-wrap:wrap}.ref{position:relative;width:96px;height:96px}.ref .el-image{width:100%;height:100%}
.zoomable{cursor:zoom-in}
.stages{margin:12px 0;padding:10px 12px;border-radius:8px;background:rgba(0,0,0,.28);border:1px solid rgba(0,0,0,.5)}
.result-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}.result-item .el-image{width:100%;height:220px}
.side .result-grid{grid-template-columns:1fr 1fr}.side .result-item .el-image{height:110px}
.hint{color:#888;font-size:12px;margin-top:4px}
.pick-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px;max-height:60vh;overflow:auto}
.pick-item{position:relative;cursor:pointer;border:2px solid transparent;border-radius:6px;overflow:hidden}
.pick-item .el-image{width:100%;height:110px;display:block}
.pick-item.sel{border-color:var(--el-color-primary)}
.pick-check{position:absolute;top:4px;right:4px;background:var(--el-color-primary);color:#fff;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;font-size:12px}
.pick-pin{position:absolute;top:4px;left:4px;background:linear-gradient(to bottom,#f6c453,#d9930d);color:#3a2703;border-radius:4px;padding:1px 6px;font-size:11px;font-weight:800;box-shadow:0 1px 3px rgba(0,0,0,.5)}
.pick-name{font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:2px 4px}
/* 左侧栏：深皮革面板 + 深色 tabs */
.side{position:sticky;top:16px;max-height:calc(100vh - 100px);overflow-y:auto;padding:14px;border-radius:12px;
  background:linear-gradient(to bottom,#2a2d33 0%,#1c1e22 100%);border:1px solid #0a0b0d;
  box-shadow:0 8px 22px rgba(0,0,0,.55), inset 0 1px 0 rgba(255,255,255,.12)}
.side :deep(.el-tabs__item){color:#b9b2a0;font-weight:600}
.side :deep(.el-tabs__item.is-active){color:#fff}
.side :deep(.el-tabs__active-bar){background:var(--el-color-primary)}
.side :deep(.el-tabs__nav-wrap::after){background:rgba(255,255,255,.09)}
/* 左侧分段切换按钮（代替 el-tabs，v-show 保留各面板状态） */
.seg{display:flex;margin-bottom:10px}
.seg button{flex:1;padding:7px 0;font-size:13px;font-weight:600;color:#e8e4d8;cursor:pointer;
  background:linear-gradient(to bottom,rgba(255,255,255,.1),rgba(255,255,255,.02) 50%,rgba(0,0,0,.14));
  border:1px solid rgba(0,0,0,.55);box-shadow:inset 0 1px 0 rgba(255,255,255,.14);text-shadow:0 -1px 0 rgba(0,0,0,.7)}
.seg button:first-child{border-radius:8px 0 0 8px}
.seg button:last-child{border-radius:0 8px 8px 0;margin-left:-1px}
.seg button.active{background:var(--gloss),var(--ios-blue);border-color:var(--ios-blue-border);color:#fff;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.5),0 1px 3px rgba(0,0,0,.5)}
/* 工作区标题行 + 窄屏入口按钮（宽屏隐藏） */
.gen-head{display:flex;align-items:center;justify-content:space-between}
.gen-head h2{margin:0}
.narrow-btns{display:none;gap:8px}
.side-head{display:none}
.side-mask{display:none}
@media (max-width:1100px){
  .narrow-btns{display:flex}
  /* 窄屏：左侧栏变左滑抽屉，两个按钮点出 */
  .side{position:fixed;left:0;top:0;bottom:0;width:min(360px,88vw);z-index:2000;max-height:none;border-radius:0;
    transform:translateX(-105%);transition:transform .25s ease;overflow-y:auto}
  .side.open{transform:none}
  .side-mask{display:block;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:1999}
  .side-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;
    color:#f5f1e6;font-weight:700;text-shadow:0 -1px 0 rgba(0,0,0,.9)}
}
</style>
