<template>
  <div class="app">
    <div class="topbar">
      <h1>OpenRouter 图像生成</h1>
      <div class="keybox">
        <input v-model="apiKey" type="password" placeholder="设置界面：输入 OpenRouter API Key (sk-or-...)" @change="saveKey" />
        <button class="btn secondary" @click="saveKey">保存 Key</button>
        <button class="btn secondary" @click="loadModels" :disabled="!apiKey || loadingModels">
          {{ loadingModels ? '加载中…' : '刷新模型' }}
        </button>
      </div>
      <div class="spacer"></div>
      <span class="status">{{ statusText }}</span>
    </div>

    <div class="main">
      <!-- 左：模型列表 -->
      <div class="col left">
        <h2>模型 ({{ filteredModels.length }}/{{ models.length }})</h2>
        <div class="field search">
          <input v-model="search" placeholder="搜索模型 id / name" />
        </div>
        <div v-if="modelsError" class="err">{{ modelsError }}</div>
        <div v-for="m in filteredModels" :key="m.id"
          class="model-card" :class="{ active: m.id === selectedId }" @click="selectModel(m.id)">
          <div class="name">{{ m.name }}</div>
          <div class="id">{{ m.id }}</div>
          <div class="meta">
            输入: {{ m.architecture.input_modalities.join(',') }} ·
            {{ m.supports_streaming ? '支持流式' : '非流式' }} ·
            参数: {{ Object.keys(m.supported_parameters).join(', ') || '—' }}
          </div>
        </div>
      </div>

      <!-- 中：提示词 + 参数 + 参考图 -->
      <div class="col center">
        <h2>生成 · {{ selectedId || '未选择模型' }}</h2>
        <div class="field">
          <label>Prompt *</label>
          <textarea v-model="prompt" class="prompt" placeholder="描述你想要的画面…" @paste="onPaste"></textarea>
          <div class="hint">支持在输入框内直接 Ctrl/Cmd+V 粘贴剪贴板图片为参考图</div>
        </div>

        <div v-if="endpoints.length" class="field">
          <label>Provider（该模型 {{ endpoints.length }} 个端点）</label>
          <select v-model="providerChoice">
            <option value="">自动路由（默认）</option>
            <option v-for="e in endpoints" :key="e.provider_slug" :value="e.provider_slug">
              {{ e.provider_name }} ({{ e.provider_slug }}) · ${{ minPrice(e) }}/图
            </option>
          </select>
          <div class="hint" v-if="activeEndpoint">
            端点参数: {{ Object.keys(activeEndpoint.supported_parameters).join(', ') }} ·
            透传: {{ activeEndpoint.allowed_passthrough_parameters.join(', ') || '无' }}
          </div>
        </div>

        <div v-for="f in paramFields" :key="f.key" class="field">
          <label>{{ f.label }} <span class="kv">{{ f.key }}</span></label>
          <select v-if="f.kind === 'enum'" v-model="paramValues[f.key]">
            <option value="">不发送（默认）</option>
            <option v-for="v in f.values" :key="v" :value="v">{{ v }}</option>
          </select>
          <div v-else-if="f.kind === 'range'" class="row">
            <input type="range" :min="f.min" :max="f.max" step="1" v-model.number="paramValues[f.key]" />
            <span>{{ paramValues[f.key] }}</span>
          </div>
          <input v-else-if="f.kind === 'number'" type="number" v-model="paramValues[f.key]" :placeholder="String(f.defaultValue ?? '')" />
          <input v-else-if="f.kind === 'text'" type="text" v-model="paramValues[f.key]" placeholder="留空不发送" />
          <label v-else-if="f.kind === 'boolean'" class="row">
            <input type="checkbox" v-model="paramValues[f.key]" /> 启用
          </label>
          <div class="hint">{{ f.hint }}</div>
        </div>

        <div class="field">
          <label>参考图片（image-to-image，可选，最多 16 张）</label>
          <div class="row" style="margin-bottom:8px">
            <button class="btn secondary" @click="pickFiles">选择文件</button>
            <input v-model="imageUrl" placeholder="或粘贴图片 URL 后点添加" style="flex:1" />
            <button class="btn secondary" @click="addUrl">添加</button>
          </div>
          <div class="refs">
            <div v-for="(r, i) in references" :key="i" class="ref">
              <img :src="r.dataUrl" :title="r.name" />
              <button @click="references.splice(i, 1)">✕</button>
            </div>
          </div>
          <div class="dropzone" @dragover.prevent @drop.prevent="onDrop" @paste="onPaste" tabindex="0">
            拖拽图片到此处 / 点击此处后 Ctrl+V 粘贴剪贴板图片
          </div>
        </div>

        <div class="row" style="display:flex;gap:8px">
          <button class="btn" @click="generate" :disabled="!canGenerate || generating">
            {{ generating ? '生成中…' : '生成图片' }}
          </button>
          <button class="btn secondary" @click="clearResults">清空结果</button>
        </div>
        <div v-if="error" class="err" style="margin-top:8px">{{ error }}</div>
        <div v-if="usageText" class="cost" style="margin-top:8px">{{ usageText }}</div>

        <div class="result" style="margin-top:12px" v-if="partialB64">
          <h2>流式预览</h2>
          <img :src="'data:image/png;base64,' + partialB64" />
        </div>

        <div style="margin-top:12px" v-if="currentImages.length">
          <h2>本次结果（{{ currentImages.length }} 张）</h2>
          <div class="result-grid">
            <div v-for="(img, i) in currentImages" :key="i" class="result-item">
              <img :src="dataUrlOf(img)" />
              <div class="row" style="display:flex;gap:6px;margin-top:6px">
                <button class="btn secondary" @click="saveImage(img, i)">保存</button>
                <button class="btn secondary" @click="useAsReference(img)">作为参考图</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右：历史 -->
      <div class="col right">
        <h2>历史（{{ history.length }}）</h2>
        <div v-if="!history.length" class="status">暂无生成记录（仅本机内存 + localStorage 缩略图不持久化大图）</div>
        <div v-for="h in history" :key="h.id" class="history-item">
          <div class="kv">{{ new Date(h.time).toLocaleString() }} · {{ h.model }}</div>
          <div class="p">{{ h.prompt }}</div>
          <div v-if="h.error" class="err">{{ h.error }}</div>
          <div v-else class="result-grid">
            <div v-for="(img, i) in h.images" :key="i" class="result-item">
              <img :src="dataUrlOf(img)" />
              <div class="row" style="display:flex;gap:6px;margin-top:6px">
                <button class="btn secondary" @click="saveImage(img, i)">保存</button>
              </div>
            </div>
          </div>
          <div v-if="h.usage" class="cost">cost: {{ h.usage.cost ?? '—' }} · tokens: {{ h.usage.total_tokens }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { listImageModels, listModelEndpoints, generateImages, generateImagesStream } from './api/openrouter'
import { buildParamFields, cleanParams, type ParamField } from './api/params'
import type { GeneratedImage, HistoryItem, ImageEndpoint, ImageModelListItem, ReferenceImage } from './api/types'

const LS_KEY = 'or-img-api-key'
const LS_HISTORY = 'or-img-history'

const apiKey = ref(localStorage.getItem(LS_KEY) || '')
const models = ref<ImageModelListItem[]>([])
const endpoints = ref<ImageEndpoint[]>([])
const search = ref('')
const selectedId = ref('')
const prompt = ref('')
const paramFields = ref<ParamField[]>([])
const paramValues = ref<Record<string, unknown>>({})
const providerChoice = ref('')
const references = ref<ReferenceImage[]>([])
const imageUrl = ref('')
const loadingModels = ref(false)
const generating = ref(false)
const modelsError = ref('')
const error = ref('')
const statusText = ref('请先在顶部设置 API Key')
const usageText = ref('')
const currentImages = ref<GeneratedImage[]>([])
const partialB64 = ref('')
const history = ref<HistoryItem[]>([])

try {
  const h = JSON.parse(localStorage.getItem(LS_HISTORY) || '[]')
  if (Array.isArray(h)) history.value = h.slice(0, 20)
} catch { /* ignore */ }

const filteredModels = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return models.value
  return models.value.filter((m) => m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q))
})
const selectedModel = computed(() => models.value.find((m) => m.id === selectedId.value))
const activeEndpoint = computed(() =>
  providerChoice.value ? endpoints.value.find((e) => e.provider_slug === providerChoice.value) : endpoints.value[0],
)
const canGenerate = computed(() => !!apiKey.value && !!selectedId.value && !!prompt.value.trim() && !generating.value)

function saveKey() {
  localStorage.setItem(LS_KEY, apiKey.value.trim())
  apiKey.value = apiKey.value.trim()
  statusText.value = apiKey.value ? 'Key 已保存' : '请先在顶部设置 API Key'
}

function minPrice(e: ImageEndpoint): string {
  const outs = e.pricing.filter((p) => p.billable === 'output_image')
  const arr = (outs.length ? outs : e.pricing).map((p) => p.cost_usd)
  return arr.length ? Math.min(...arr).toFixed(4) : '?'
}

async function loadModels() {
  if (!apiKey.value) { modelsError.value = '请先填写 API Key'; return }
  loadingModels.value = true
  modelsError.value = ''
  try {
    models.value = await listImageModels(apiKey.value)
    statusText.value = `已加载 ${models.value.length} 个图像模型`
    if (!selectedId.value && models.value.length) selectModel(models.value[0].id)
  } catch (e) {
    modelsError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loadingModels.value = false
  }
}

async function selectModel(id: string) {
  selectedId.value = id
  providerChoice.value = ''
  paramFields.value = []
  paramValues.value = {}
  endpoints.value = []
  const m = models.value.find((x) => x.id === id)
  // 先用模型级 supported_parameters 给默认值
  if (m) applyFields(m.supported_parameters)
  // 再拉端点级精确参数（取所选 provider 或首个端点的交集展示）
  try {
    const eps = await listModelEndpoints(apiKey.value, id)
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
  const next: Record<string, unknown> = keepValues ? { ...paramValues.value } : {}
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

// ---- 参考图：文件选择 / 拖拽 / 剪贴板粘贴 ----
async function pickFiles() {
  if (window.electronAPI) {
    const pics = await window.electronAPI.pickImages()
    references.value.push(...pics.slice(0, 16 - references.value.length))
    return
  }
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*'
  input.multiple = true
  input.onchange = () => {
    if (!input.files) return
    for (const f of Array.from(input.files).slice(0, 16 - references.value.length)) {
      const rd = new FileReader()
      rd.onload = () => references.value.push({ name: f.name, dataUrl: String(rd.result) })
      rd.readAsDataURL(f)
    }
  }
  input.click()
}

function addUrl() {
  const u = imageUrl.value.trim()
  if (!u) return
  references.value.push({ name: u.slice(0, 40), dataUrl: u })
  imageUrl.value = ''
}

function filesToRefs(files: FileList | File[]) {
  for (const f of Array.from(files).slice(0, 16 - references.value.length)) {
    if (!f.type.startsWith('image/')) continue
    const rd = new FileReader()
    rd.onload = () => references.value.push({ name: f.name, dataUrl: String(rd.result) })
    rd.readAsDataURL(f)
  }
}

function onDrop(e: DragEvent) {
  if (e.dataTransfer?.files?.length) filesToRefs(e.dataTransfer.files)
}

function onPaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  for (const it of Array.from(items)) {
    if (it.type.startsWith('image/')) {
      const f = it.getAsFile()
      if (f) {
        e.preventDefault()
        filesToRefs([f])
      }
    }
  }
}

document.addEventListener('paste', (e) => {
  // 全局兜底：剪贴板图片直接作为参考图
  const items = e.clipboardData?.items
  if (!items) return
  const target = e.target as HTMLElement
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) {
    // 输入框内的粘贴由 onPaste 处理，避免重复
    return
  }
  for (const it of Array.from(items)) {
    if (it.type.startsWith('image/')) {
      const f = it.getAsFile()
      if (f) filesToRefs([f])
    }
  }
})

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
        } else if (ev.type === 'error') {
          throw new Error(ev.error?.message || '流式生成失败')
        }
      })
      if (!currentImages.value.length && !error.value) {
        // 某些端点忽略 stream，走缓冲需再请求一次由服务端判断；此处提示即可
        statusText.value = '流式无 completed 事件，可能端点不支持 stream'
      }
    } else {
      const res = await generateImages(apiKey.value, body)
      currentImages.value = res.data
      if (res.usage) usageText.value = `cost: $${res.usage.cost ?? '?'} · tokens: ${res.usage.total_tokens}`
      pushHistory({ images: res.data, usage: res.usage })
      statusText.value = `生成完成：${res.data.length} 张`
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    error.value = msg
    pushHistory({ images: [], error: msg })
  } finally {
    generating.value = false
  }
}

function pushHistory(h: { images: GeneratedImage[]; usage?: HistoryItem['usage']; error?: string }) {
  history.value.unshift({
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    time: Date.now(),
    model: selectedId.value,
    prompt: prompt.value.trim(),
    images: h.images,
    usage: h.usage,
    error: h.error,
  })
  history.value = history.value.slice(0, 20)
  try {
    // 大图 base64 不进 localStorage，只存元信息
    localStorage.setItem(LS_HISTORY, JSON.stringify(history.value.map((x) => ({ ...x, images: [] }))))
  } catch { /* ignore */ }
}

function clearResults() {
  currentImages.value = []
  partialB64.value = ''
  error.value = ''
  usageText.value = ''
}

async function saveImage(img: GeneratedImage, i: number) {
  const b64 = img.b64_json.startsWith('data:') ? img.b64_json.split(',')[1] : img.b64_json
  if (window.electronAPI) {
    const r = await window.electronAPI.saveImage({
      b64,
      mediaType: img.media_type,
      suggestedName: `or-${selectedId.value.replace('/', '-')}-${Date.now()}-${i}.png`,
    })
    if (r.saved) statusText.value = `已保存：${r.path}`
    return
  }
  const a = document.createElement('a')
  a.href = dataUrlOf(img)
  a.download = `or-image-${Date.now()}-${i}.png`
  a.click()
}

function useAsReference(img: GeneratedImage) {
  references.value.push({ name: '生成结果', dataUrl: dataUrlOf(img) })
}

onMounted(() => {
  if (apiKey.value) loadModels()
})
</script>
