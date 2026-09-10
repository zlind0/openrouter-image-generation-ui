<template>
  <div class="app">
    <!-- 自绘标题栏：Win/Linux frameless 右置原生按钮替代，macOS 左侧给红绿灯留位 -->
    <div class="titlebar" :class="{ mac: isMac }" data-tauri-drag-region @dblclick="onTitleDblClick">
      <div class="tb-title">OpenRouter ImageGen UI</div>
      <div class="tb-btns" v-if="isFrameless">
        <button class="tb-btn" title="最小化" @click="minWin"><el-icon><Minus /></el-icon></button>
        <button class="tb-btn" :title="isMaxed ? '还原' : '最大化'" @click="toggleMaxWin">
          <el-icon><CopyDocument v-if="isMaxed" /><FullScreen v-else /></el-icon>
        </button>
        <button class="tb-btn danger" title="关闭" @click="closeWin"><el-icon><Close /></el-icon></button>
      </div>
    </div>
    <div class="topbar">
      <el-select
        v-model="selectedId"
        filterable
        :filter-method="filterModels"
        placeholder="选择模型"
        class="model-picker"
        popper-class="model-picker-popper"
        :loading="loadingModels"
        @change="selectModel"
      >
        <el-option v-for="m in filteredModels" :key="m.id" :label="m.name" :value="m.id">
          <div class="opt-name">{{ m.name }}</div>
          <div class="opt-id">{{ m.id }}</div>
        </el-option>
      </el-select>
      <el-button :icon="Setting" @click="openSettings">设置</el-button>
      <el-button @click="loadModels" :loading="loadingModels" :disabled="!apiKey">刷新模型</el-button>
      <div class="spacer"></div>
      <span class="balance" :title="balanceTip">{{ balanceText }}</span>
      <el-button circle size="small" :icon="Refresh" title="刷新余额" @click="() => refreshBalance()" :loading="loadingBalance" />
      <span class="status">{{ statusText }}</span>
    </div>

    <div class="main">
      <!-- 中：提示词 + 参数 + 参考图 -->
      <div class="col center">
        <h2>生成 · {{ selectedId || '未选择模型' }}</h2>
        <div class="field">
          <label>Prompt *</label>
          <el-input v-model="prompt" type="textarea" :rows="5" placeholder="描述你想要的画面…" />
          <div class="hint">任意位置 Ctrl/Cmd+V 粘贴剪贴板图片即可作为参考图</div>
        </div>

        <div v-if="endpoints.length" class="field">
          <label>Provider（该模型 {{ endpoints.length }} 个端点）</label>
          <el-select v-model="providerChoice" clearable placeholder="自动路由（默认）" style="width: 100%">
            <el-option label="自动路由（默认）" value="" />
            <el-option
              v-for="e in endpoints"
              :key="e.provider_slug"
              :label="`${e.provider_name} (${e.provider_slug}) · $${minPrice(e)}/图`"
              :value="e.provider_slug"
            />
          </el-select>
          <div class="hint" v-if="activeEndpoint">
            端点参数: {{ Object.keys(activeEndpoint.supported_parameters).join(', ') }} ·
            透传: {{ activeEndpoint.allowed_passthrough_parameters.join(', ') || '无' }}
          </div>
        </div>

        <div v-for="f in paramFields" :key="f.key" class="field">
          <label>{{ f.label }} <span class="kv">{{ f.key }}</span></label>
          <el-select
            v-if="f.kind === 'enum'"
            v-model="paramValues[f.key]"
            clearable
            placeholder="不发送（默认）"
            style="width: 100%"
          >
            <el-option v-for="v in f.values" :key="v" :label="v" :value="v" />
          </el-select>
          <el-slider
            v-else-if="f.kind === 'range'"
            v-model="paramValues[f.key]"
            :min="f.min ?? 0"
            :max="f.max ?? 10"
            :step="1"
            show-input
            :show-input-controls="false"
          />
          <el-input-number
            v-else-if="f.kind === 'number'"
            v-model="paramValues[f.key]"
            controls-position="right"
            style="width: 100%"
            :placeholder="String(f.defaultValue ?? '')"
          />
          <el-input
            v-else-if="f.kind === 'text'"
            v-model="paramValues[f.key]"
            placeholder="留空不发送"
            clearable
          />
          <div v-else-if="f.kind === 'boolean'"><el-switch v-model="paramValues[f.key]" /></div>
          <div class="hint">{{ f.hint }}</div>
        </div>

        <div class="field">
          <label>参考图片（image-to-image，可选，最多 16 张，点击放大）</label>
          <div class="row" style="margin-bottom: 8px">
            <el-button :icon="FolderOpened" @click="pickFiles">选择文件</el-button>
            <el-input v-model="imageUrl" placeholder="或粘贴图片 URL 后点添加" style="flex: 1">
              <template #append><el-button @click="addUrl">添加</el-button></template>
            </el-input>
          </div>
          <div class="refs">
            <div v-for="(r, i) in references" :key="i" class="ref">
              <el-image
                :src="r.dataUrl"
                fit="cover"
                :preview-src-list="refsPreview"
                :initial-index="i"
                :title="r.name"
              />
              <el-button class="ref-del" size="small" circle :icon="Close" type="danger" @click="references.splice(i, 1)" />
            </div>
          </div>
          <div class="dropzone" @dragover.prevent @drop.prevent="onDrop" tabindex="0">
            拖拽图片到此处 / 任意位置 Ctrl+V 粘贴剪贴板图片
          </div>
        </div>

        <div class="row" style="display: flex; gap: 8px">
          <el-button type="primary" :loading="generating" :disabled="!canGenerate" @click="generate">
            {{ generating ? '生成中…' : '生成图片' }}
          </el-button>
          <el-button @click="clearResults">清空结果</el-button>
        </div>
        <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" style="margin-top: 8px" />
        <div v-if="usageText" class="cost" style="margin-top: 8px">{{ usageText }}</div>

        <div class="result" style="margin-top: 12px" v-if="partialB64">
          <h2>流式预览</h2>
          <el-image
            :src="'data:image/png;base64,' + partialB64"
            fit="contain"
            :preview-src-list="['data:image/png;base64,' + partialB64]"
          />
        </div>

        <div style="margin-top: 12px" v-if="currentImages.length">
          <h2>本次结果（{{ currentImages.length }} 张，点击放大）</h2>
          <div class="result-grid">
            <div v-for="(img, i) in currentImages" :key="i" class="result-item">
              <el-image :src="dataUrlOf(img)" fit="cover" :preview-src-list="currentPreview" :initial-index="i" />
              <div class="row" style="display: flex; gap: 6px; margin-top: 6px">
                <el-button size="small" :icon="Download" @click="saveImage(img, i)">保存</el-button>
                <el-button size="small" :icon="Picture" @click="useAsReference(img)">作为参考图</el-button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右：历史 -->
      <div class="col right">
        <div class="h-title">
          <h2>历史（{{ history.length }}，点击还原）</h2>
          <el-button v-if="history.length" size="small" type="danger" :icon="Delete" @click="clearHistory">清空</el-button>
        </div>
        <el-empty v-if="!history.length" description="暂无生成记录" />
        <el-alert v-if="modelsError" :title="modelsError" type="error" show-icon :closable="false" style="margin-bottom: 10px" />
        <el-card
          v-for="h in history"
          :key="h.id"
          class="history-item"
          shadow="hover"
          @click="restoreHistory(h)"
        >
          <template #header>
            <div class="h-head">
              <div class="kv">{{ new Date(h.time).toLocaleString() }} · {{ h.model }}</div>
              <el-button size="small" type="danger" :icon="Delete" circle @click.stop="deleteHistory(h.id)" />
            </div>
          </template>
          <div class="p">{{ h.prompt }}</div>
          <el-alert v-if="h.error" :title="h.error" type="error" show-icon :closable="false" />
          <div v-else class="result-grid">
            <div v-for="(img, i) in h.images" :key="i" class="result-item">
              <el-image
                :src="dataUrlOf(img)"
                fit="cover"
                :preview-src-list="h.images.map(dataUrlOf)"
                :initial-index="i"
                @click.stop
              />
              <div class="row" style="display: flex; gap: 6px; margin-top: 6px">
                <el-button size="small" :icon="Download" @click.stop="saveImage(img, i)">保存</el-button>
              </div>
            </div>
          </div>
          <div v-if="h.usage" class="cost">cost: {{ h.usage.cost ?? '—' }} · tokens: {{ h.usage.total_tokens }}</div>
        </el-card>
      </div>
    </div>

    <!-- 设置：BaseURL / Key / 代理 -->
    <el-dialog v-model="settingsOpen" title="设置" width="520px" :close-on-click-modal="false">
      <el-form label-width="86px" label-position="left">
        <el-form-item label="Base URL">
          <el-input v-model="draftBaseUrl" placeholder="https://openrouter.ai/api/v1" clearable />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="draftKey" type="password" show-password placeholder="sk-or-..." clearable />
        </el-form-item>
        <el-divider>代理（浏览器预览时不生效）</el-divider>
        <el-form-item label="启用代理">
          <el-switch v-model="draftProxy.enabled" @change="onProxyToggle" />
        </el-form-item>
        <el-form-item label="代理类型">
          <el-select v-model="draftProxy.type" :disabled="!draftProxy.enabled" style="width: 100%">
            <el-option label="HTTP" value="http" />
            <el-option label="HTTPS" value="https" />
            <el-option label="SOCKS5" value="socks5" />
          </el-select>
        </el-form-item>
        <el-form-item label="代理地址">
          <el-input v-model="draftProxy.url" :disabled="!draftProxy.enabled" placeholder="127.0.0.1:7890" clearable />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="draftProxy.username" :disabled="!draftProxy.enabled" placeholder="可选" clearable />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="draftProxy.password"
            :disabled="!draftProxy.enabled"
            type="password"
            show-password
            placeholder="可选"
            clearable
          />
        </el-form-item>
        <el-alert v-if="testResult" :title="testResult" type="success" show-icon :closable="false" />
      </el-form>
      <template #footer>
        <el-button @click="testConnection" :loading="testing">测试连接</el-button>
        <el-button @click="settingsOpen = false">取消</el-button>
        <el-button type="primary" @click="saveSettingsDialog">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close, CopyDocument, Delete, Download, FolderOpened, FullScreen, Minus, Picture, Refresh, Setting } from '@element-plus/icons-vue'
import { listImageModels, listModelEndpoints, generateImages, generateImagesStream, getKeyInfo } from './api/openrouter'
import { isTauri } from '@tauri-apps/api/core'
import {
  isMacOS,
  pickImages as nativePickImages,
  saveImage as nativeSaveImage,
  fetchImageDataUrl,
  minimizeWin as nativeMinimize,
  toggleMaxWin as nativeToggleMax,
  closeWin as nativeClose,
  getMaxed,
  onMaxState,
} from './api/native'
import { loadSettings, saveSettings, loadLastModel, saveLastModel, DEFAULT_BASE_URL, DEFAULT_PROXY_URL, type ProxySettings } from './api/settings'
import { loadHistory, persistHistory } from './api/historyStore'
import { buildParamFields, cleanParams, type ParamField } from './api/params'
import type { GeneratedImage, HistoryItem, ImageEndpoint, ImageModelListItem, ReferenceImage } from './api/types'

const stored = loadSettings()

const apiKey = ref(stored.apiKey)
const baseUrl = ref(stored.baseUrl || DEFAULT_BASE_URL)
const proxyCfg = ref<ProxySettings>({ ...stored.proxy })
const models = ref<ImageModelListItem[]>([])
const endpoints = ref<ImageEndpoint[]>([])
const modelQuery = ref('')
const selectedId = ref('')
const prompt = ref('')
const paramFields = ref<ParamField[]>([])
/* 动态表单值：key 类型随参数变化，用 any 简化各组件 v-model 绑定 */
const paramValues = ref<Record<string, any>>({})
const providerChoice = ref('')
const references = ref<ReferenceImage[]>([])
const imageUrl = ref('')
const loadingModels = ref(false)
const generating = ref(false)
const modelsError = ref('')
const error = ref('')
const statusText = ref('请先打开设置配置 API Key')
const balanceText = ref('余额：—')
const balanceTip = ref('')
const loadingBalance = ref(false)
const usageText = ref('')
const currentImages = ref<GeneratedImage[]>([])
const partialB64 = ref('')
const history = ref<HistoryItem[]>([])

// 自绘标题栏：macOS 左侧红绿灯，Win/Linux 无边框右置按钮（Tauri 下 data-tauri-drag-region 拖拽）
const isMac = ref(isMacOS())
const isFrameless = ref(isTauri() && !isMacOS())
const isMaxed = ref(false)
function onTitleDblClick() {
  if (isFrameless.value) toggleMaxWin()
}
function syncMaxed() {
  getMaxed()
    .then((v) => {
      isMaxed.value = v
    })
    .catch(() => {})
}
function minWin() {
  void nativeMinimize()
}
function toggleMaxWin() {
  nativeToggleMax()
    .then(syncMaxed)
    .catch(() => {})
}
function closeWin() {
  void nativeClose()
}

function filterModels(q: string) {
  modelQuery.value = q
}
const filteredModels = computed(() => {
  const q = modelQuery.value.trim().toLowerCase()
  if (!q) return models.value
  return models.value.filter((m) => m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q))
})
const activeEndpoint = computed(() =>
  providerChoice.value ? endpoints.value.find((e) => e.provider_slug === providerChoice.value) : endpoints.value[0],
)
const canGenerate = computed(() => !!apiKey.value && !!selectedId.value && !!prompt.value.trim() && !generating.value)
const refsPreview = computed(() => references.value.map((r) => r.dataUrl))
const currentPreview = computed(() => currentImages.value.map(dataUrlOf))

/* ---- 设置：BaseURL / Key / 代理 ---- */
const settingsOpen = ref(false)
const draftBaseUrl = ref('')
const draftKey = ref('')
const draftProxy = ref<ProxySettings>({ enabled: false, type: 'http', url: '', username: '', password: '' })
const testing = ref(false)
const testResult = ref('')

function openSettings() {
  draftBaseUrl.value = baseUrl.value
  draftKey.value = apiKey.value
  draftProxy.value = { ...proxyCfg.value }
  // 老配置里地址可能是空的，打开即补默认，不用手打
  if (!draftProxy.value.url.trim()) draftProxy.value.url = DEFAULT_PROXY_URL
  testResult.value = ''
  settingsOpen.value = true
}

function onProxyToggle() {
  if (draftProxy.value.enabled && !draftProxy.value.url.trim()) {
    draftProxy.value.url = DEFAULT_PROXY_URL
  }
}

async function testConnection() {
  const key = draftKey.value.trim()
  const url = (draftBaseUrl.value.trim() || DEFAULT_BASE_URL).replace(/\/+$/, '')
  if (!key) {
    ElMessage.warning('请先填写 API Key')
    return
  }
  if (draftProxy.value.enabled && !draftProxy.value.url.trim()) {
    ElMessage.warning('已启用代理，请填写代理地址')
    return
  }
  const inTauri = isTauri()
  if (!inTauri && draftProxy.value.enabled) {
    ElMessage.warning('浏览器预览时代理不生效，本次测试走直连')
  }
  testing.value = true
  testResult.value = ''
  // 代理随调用传入，测的就是界面上当前填的值，无需临时切换
  try {
    // 测试即拉模型：通则可用模型数即结果
    const list = await listImageModels(key, url, { ...draftProxy.value })
    testResult.value = `连接成功，可用图像模型 ${list.length} 个`
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    testing.value = false
  }
}

async function saveSettingsDialog() {
  const key = draftKey.value.trim()
  const url = (draftBaseUrl.value.trim() || DEFAULT_BASE_URL).replace(/\/+$/, '')
  if (!key) {
    ElMessage.warning('请填写 API Key')
    return
  }
  if (draftProxy.value.enabled && !draftProxy.value.url.trim()) {
    ElMessage.warning('已启用代理，请填写代理地址')
    return
  }
  apiKey.value = key
  baseUrl.value = url
  proxyCfg.value = { ...draftProxy.value }
  saveSettings({ baseUrl: url, apiKey: key, proxy: { ...proxyCfg.value } })
  settingsOpen.value = false
  ElMessage.success('设置已保存')
  await loadModels()
  await refreshBalance(true)
}

/* ---- 余额：打开 App / 生成完成后刷新，支持手动刷新 ---- */
async function refreshBalance(silent = false) {
  if (!apiKey.value) {
    balanceText.value = '余额：—'
    balanceTip.value = '请先在设置中配置 API Key'
    return
  }
  loadingBalance.value = true
  try {
    const info = await getKeyInfo(apiKey.value, baseUrl.value, proxyCfg.value)
    if (info.limit_remaining == null) {
      balanceText.value = `已用 $${info.usage.toFixed(2)}（不限额）`
    } else {
      balanceText.value = `剩余额度 $${info.limit_remaining.toFixed(2)}`
    }
    balanceTip.value = `${info.label || 'Key'} · 累计已用 $${info.usage.toFixed(2)} · 今日 $${info.usage_daily.toFixed(2)}`
  } catch (e) {
    balanceText.value = '余额获取失败'
    balanceTip.value = e instanceof Error ? e.message : String(e)
    if (!silent) ElMessage.error(balanceTip.value)
  } finally {
    loadingBalance.value = false
  }
}

function minPrice(e: ImageEndpoint): string {
  const outs = e.pricing.filter((p) => p.billable === 'output_image')
  const arr = (outs.length ? outs : e.pricing).map((p) => p.cost_usd)
  return arr.length ? Math.min(...arr).toFixed(4) : '?'
}

async function loadModels() {
  if (!apiKey.value) {
    modelsError.value = '请先填写 API Key'
    return
  }
  loadingModels.value = true
  modelsError.value = ''
  try {
    models.value = await listImageModels(apiKey.value, baseUrl.value, proxyCfg.value)
    statusText.value = `已加载 ${models.value.length} 个图像模型`
    ElMessage.success(`已加载 ${models.value.length} 个图像模型`)
    if (!selectedId.value && models.value.length) {
      // 优先恢复上次选择过的模型（下拉选中即记），找不到了再回退第一个
      const last = loadLastModel()
      const hit = last && models.value.some((m) => m.id === last) ? last : models.value[0].id
      selectModel(hit)
    }
  } catch (e) {
    modelsError.value = e instanceof Error ? e.message : String(e)
    ElMessage.error(modelsError.value)
  } finally {
    loadingModels.value = false
  }
}

async function selectModel(id: string) {
  if (!id) return
  selectedId.value = id
  saveLastModel(id)
  providerChoice.value = ''
  paramFields.value = []
  paramValues.value = {}
  endpoints.value = []
  const m = models.value.find((x) => x.id === id)
  // 先用模型级 supported_parameters 给默认值
  if (m) applyFields(m.supported_parameters)
  // 再拉端点级精确参数
  try {
    const eps = await listModelEndpoints(apiKey.value, id, baseUrl.value, proxyCfg.value)
    endpoints.value = eps
    const ep = eps[0]
    if (ep) applyFields(ep.supported_parameters)
  } catch (e) {
    statusText.value = e instanceof Error ? e.message : String(e)
  }
}

watch(providerChoice, () => {
  const ep = activeEndpoint.value
  if (ep) applyFields(ep.supported_parameters, true)
})

function applyFields(supported: Record<string, unknown> | undefined, keepValues = false) {
  if (!supported) return
  const fields = buildParamFields(supported as Record<string, never>)
  paramFields.value = fields
  const next: Record<string, any> = keepValues ? { ...paramValues.value } : {}
  for (const f of fields) {
    if (!(f.key in next)) next[f.key] = f.defaultValue
  }
  paramValues.value = next
}

function dataUrlOf(img: GeneratedImage): string {
  if (img.b64_json.startsWith('data:') || img.b64_json.startsWith('http')) return img.b64_json
  const mime = img.media_type || 'image/png'
  if (mime === 'image/svg+xml') return `data:image/svg+xml;base64,${img.b64_json}`
  return `data:${mime};base64,${img.b64_json}`
}

// ---- 参考图：文件选择 / 拖拽 / 剪贴板粘贴（单一 document 监听，避免重复） ----
async function pickFiles() {
  // Tauri 原生对话框 / 浏览器 input 都在 native 内处理
  const pics = await nativePickImages()
  references.value.push(...pics.slice(0, 16 - references.value.length))
}

function addUrl() {
  const u = imageUrl.value.trim()
  if (!u) return
  imageUrl.value = ''
  void addUrlAsync(u)
}

async function addUrlAsync(u: string) {
  if (references.value.length >= 16) {
    ElMessage.warning('参考图最多 16 张')
    return
  }
  // 经 Rust 拉图（走已配置代理）转 dataURL 后再预览/上传，
  // 全程不依赖 OpenRouter 服务端去抓 URL；失败则保留原 URL
  if (/^https?:\/\//i.test(u)) {
    try {
      const dataUrl = await fetchImageDataUrl(u, proxyCfg.value)
      references.value.push({ name: u.slice(0, 40), dataUrl })
      return
    } catch (e) {
      ElMessage.warning(`代理拉图失败，已保留原 URL：${e instanceof Error ? e.message : String(e)}`)
    }
  }
  references.value.push({ name: u.slice(0, 40), dataUrl: u })
}

// 2 秒内同名同大小同时间戳的文件视为重复事件，去重
const recentFiles = new Set<string>()

function filesToRefs(files: FileList | File[]) {
  for (const f of Array.from(files).slice(0, 16 - references.value.length)) {
    if (!f.type.startsWith('image/')) continue
    const key = `${f.name}|${f.size}|${f.lastModified}`
    if (recentFiles.has(key)) continue
    recentFiles.add(key)
    setTimeout(() => recentFiles.delete(key), 2000)
    const rd = new FileReader()
    rd.onload = () => references.value.push({ name: f.name, dataUrl: String(rd.result) })
    rd.readAsDataURL(f)
  }
}

function onDrop(e: DragEvent) {
  if (e.dataTransfer?.files?.length) filesToRefs(e.dataTransfer.files)
}

/** 全局唯一粘贴入口：有图片才拦截，无图片放行（保证文本正常粘贴）。 */
function handlePaste(e: ClipboardEvent) {
  if (e.defaultPrevented) return
  const files: File[] = []
  const items = e.clipboardData?.items
  if (items) {
    for (const it of Array.from(items)) {
      if (it.kind === 'file' && it.type.startsWith('image/')) {
        const f = it.getAsFile()
        if (f) files.push(f)
      }
    }
  }
  if (!files.length && e.clipboardData?.files?.length) {
    for (const f of Array.from(e.clipboardData.files)) {
      if (f.type.startsWith('image/')) files.push(f)
    }
  }
  if (!files.length) return
  e.preventDefault()
  filesToRefs(files)
}

// ---- 生成 ----
async function generate() {
  if (!canGenerate.value) return
  generating.value = true
  error.value = ''
  usageText.value = ''
  currentImages.value = []
  partialB64.value = ''
  const cleaned = cleanParams(paramValues.value)
  const body = {
    model: selectedId.value,
    prompt: prompt.value.trim(),
    ...cleaned,
    input_references: references.value.length
      ? references.value.map((r) => ({ type: 'image_url' as const, image_url: { url: r.dataUrl } }))
      : undefined,
    provider: providerChoice.value ? { only: [providerChoice.value] } : undefined,
  }
  const useStream = cleaned.stream === true
  try {
    if (useStream) {
      await generateImagesStream(apiKey.value, body, (ev) => {
        if (ev.type === 'image_generation.partial_image' && ev.b64_json) partialB64.value = ev.b64_json
        else if (ev.type === 'image_generation.completed' && ev.b64_json) {
          currentImages.value = [{ b64_json: ev.b64_json, media_type: ev.media_type }]
          if (ev.usage) usageText.value = `cost: $${ev.usage.cost ?? '?'} · tokens: ${ev.usage.total_tokens}`
          pushHistory({ images: currentImages.value, usage: ev.usage })
          void refreshBalance(true)
        } else if (ev.type === 'error') {
          throw new Error(ev.error?.message || '流式生成失败')
        }
      }, baseUrl.value, proxyCfg.value)
      if (!currentImages.value.length && !error.value) {
        statusText.value = '流式无 completed 事件，可能端点不支持 stream'
      }
    } else {
      const res = await generateImages(apiKey.value, body, baseUrl.value, proxyCfg.value)
      currentImages.value = res.data
      if (res.usage) usageText.value = `cost: $${res.usage.cost ?? '?'} · tokens: ${res.usage.total_tokens}`
      pushHistory({ images: res.data, usage: res.usage })
      statusText.value = `生成完成：${res.data.length} 张`
      ElMessage.success(`生成完成：${res.data.length} 张`)
      void refreshBalance(true)
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    error.value = msg
    ElMessage.error(msg)
    pushHistory({ images: [], error: msg })
  } finally {
    generating.value = false
  }
}

// ---- 历史：IndexedDB 全量持久化（含图），点击还原，单条删除 ----
function pushHistory(h: { images: GeneratedImage[]; usage?: HistoryItem['usage']; error?: string }) {
  history.value.unshift({
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    time: Date.now(),
    model: selectedId.value,
    prompt: prompt.value.trim(),
    images: h.images,
    usage: h.usage,
    error: h.error,
    params: { ...paramValues.value },
    providerChoice: providerChoice.value,
    references: references.value.map((r) => ({ ...r })),
  })
  history.value = history.value.slice(0, 50)
  persistHistory(history.value).catch((e) => {
    statusText.value = `历史保存失败：${e instanceof Error ? e.message : String(e)}`
  })
}

async function restoreHistory(h: HistoryItem) {
  prompt.value = h.prompt
  references.value = (h.references ?? []).map((r) => ({ ...r }))
  currentImages.value = [...h.images]
  error.value = h.error ?? ''
  usageText.value = h.usage ? `cost: $${h.usage.cost ?? '?'} · tokens: ${h.usage.total_tokens}` : ''
  if (h.model !== selectedId.value) await selectModel(h.model)
  if (h.params) {
    for (const [k, v] of Object.entries(h.params)) paramValues.value[k] = v
  }
  providerChoice.value = h.providerChoice ?? ''
  statusText.value = `已还原：${h.model}`
  ElMessage.success(`已还原：${h.model}`)
  document.querySelector('.col.center')?.scrollTo({ top: 0 })
}

function deleteHistory(id: string) {
  history.value = history.value.filter((h) => h.id !== id)
  persistHistory(history.value).catch(() => {})
  ElMessage.success('已删除该条历史')
}

async function clearHistory() {
  try {
    await ElMessageBox.confirm(`确定删除全部 ${history.value.length} 条历史吗？`, '清空历史', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  history.value = []
  persistHistory(history.value).catch(() => {})
}

function clearResults() {
  currentImages.value = []
  partialB64.value = ''
  error.value = ''
  usageText.value = ''
}

async function saveImage(img: GeneratedImage, i: number) {
  const b64 = img.b64_json.startsWith('data:') ? img.b64_json.split(',')[1] : img.b64_json
  // Tauri 原生另存为 / 浏览器 a[download] 都在 native 内处理
  const r = await nativeSaveImage({
    b64,
    mediaType: img.media_type,
    suggestedName: `or-${selectedId.value.replace('/', '-')}-${Date.now()}-${i}.png`,
  })
  if (r.saved) {
    statusText.value = `已保存：${r.path}`
    ElMessage.success(`已保存：${r.path}`)
  }
}

function useAsReference(img: GeneratedImage) {
  references.value.push({ name: '生成结果', dataUrl: dataUrlOf(img) })
  ElMessage.success('已加入参考图')
}

onMounted(async () => {
  document.addEventListener('paste', handlePaste)
  // frameless 下同步最大化状态（Rust 在 resize 时推送事件）
  onMaxState((v) => {
    isMaxed.value = v
  })
  syncMaxed()
  try {
    history.value = await loadHistory()
  } catch {
    history.value = []
  }
  // 兼容旧版本 localStorage 历史（仅元信息），合并后清理
  try {
    const legacy = JSON.parse(localStorage.getItem('or-img-history') || '[]')
    if (Array.isArray(legacy) && legacy.length && !history.value.length) {
      history.value = legacy.slice(0, 50)
      persistHistory(history.value).catch(() => {})
    }
    localStorage.removeItem('or-img-history')
  } catch { /* ignore */ }
  // 打开 App 即拉模型 + 刷余额（代理随每次 Rust 调用传入，无需预应用）
  if (apiKey.value) {
    loadModels()
    void refreshBalance(true)
  }
})

onUnmounted(() => {
  document.removeEventListener('paste', handlePaste)
})
</script>
