<template>
  <div class="gen">
    <h2>图片生成</h2>
    <div class="topbar">
      <el-select v-model="selectedId" filterable placeholder="选择模型" style="width:320px" :loading="loadingModels" @change="selectModel">
        <el-option v-for="m in models" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-button @click="loadModels" :loading="loadingModels">刷新模型</el-button>
      <span class="balance">{{ balanceText }}</span>
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
    <div class="field"><label>参考图（可选）</label>
      <div class="row"><el-button @click="pickFiles">选择文件</el-button>
        <el-input v-model="imageUrl" placeholder="图片 URL"><template #append><el-button @click="addUrl">添加</el-button></template></el-input>
      </div>
      <div class="refs"><div v-for="(r,i) in references" :key="i" class="ref">
        <el-image :src="r.dataUrl" fit="cover" /><el-button size="small" circle type="danger" @click="references.splice(i,1)">×</el-button>
      </div></div>
    </div>
    <el-button type="primary" :loading="generating" :disabled="!canGenerate" @click="generate">{{ generating?'生成中…':'生成图片' }}</el-button>
    <el-alert v-if="error" :title="error" type="error" :closable="false" style="margin-top:8px" />
    <div v-if="usageText" style="margin-top:8px">{{ usageText }}</div>
    <div v-if="currentImages.length" class="result-grid" style="margin-top:12px">
      <div v-for="(img,i) in currentImages" :key="i" class="result-item">
        <el-image :src="dataUrlOf(img)" fit="cover" :preview-src-list="currentImages.map(dataUrlOf)" />
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
          <div class="hint">默认进入「上传素材」库</div>
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
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, orApi } from '../api/client'
import { pickImages, saveImage as dl } from '../api/native'
import { buildParamFields, cleanParams, type ParamField } from '../api/params'

const models = ref<any[]>([])
const endpoints = ref<any[]>([])
const selectedId = ref('')
const prompt = ref('')
const paramFields = ref<ParamField[]>([])
const paramValues = ref<Record<string, any>>({})
const providerChoice = ref('')
const references = ref<{name:string;dataUrl:string}[]>([])
const imageUrl = ref('')
const loadingModels = ref(false)
const generating = ref(false)
const error = ref('')
const balanceText = ref('')
const usageText = ref('')
const currentImages = ref<{b64_json:string;media_type?:string}[]>([])
const folders = ref<any[]>([])
// 点击入库弹窗状态（生成结果默认不入库，只能逐张手动入库）
const stockOpen = ref(false)
const stocking = ref(false)
const stockImg = ref<{b64_json:string;media_type?:string}|null>(null)
const stockFolder = ref('')
const stockTags = ref('')

const canGenerate = computed(() => !!selectedId.value && !!prompt.value.trim() && !generating.value)

async function loadModels() {
  loadingModels.value = true
  try {
    const list = await orApi.models()
    models.value = Array.isArray(list) ? list : []
    const info = await orApi.keyInfo().catch(() => null)
    if (info) balanceText.value = info.limit_remaining != null ? `剩余额度 $${info.limit_remaining.toFixed(2)}` : `已用 $${info.usage?.toFixed?.(2) ?? '?'}`;
    try { folders.value = (await api.get('/api/assets/folders')).data } catch {}
  // 入库默认文件夹：有「上传素材」则预选
  if (!stockFolder.value) {
    const hit = folders.value.find((f: any) => f.path === '上传素材' || f.name === '上传素材')
    if (hit) stockFolder.value = hit.id
  }
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || e.message) }
  finally { loadingModels.value = false }
}
async function selectModel(id: string) {
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
function dataUrlOf(img: any) {
  if (img.b64_json.startsWith('data:') || img.b64_json.startsWith('http')) return img.b64_json
  return `data:${img.media_type || 'image/png'};base64,${img.b64_json}`
}
async function pickFiles() { references.value.push(...(await pickImages())) }
async function addUrl() {
  const u = imageUrl.value.trim(); if (!u) return; imageUrl.value = ''
  try { const res = await fetch(u); const blob = await res.blob()
    const rd = new FileReader(); rd.onload = () => references.value.push({ name: u.slice(0,40), dataUrl: String(rd.result) }); rd.readAsDataURL(blob)
  } catch { references.value.push({ name: u.slice(0,40), dataUrl: u }) }
}
async function generate() {
  if (!canGenerate.value) return
  generating.value = true; error.value=''; usageText.value=''; currentImages.value=[]
  const cleaned = cleanParams(paramValues.value)
  const { stream, ...rest } = cleaned as any
  const body = {
    model: selectedId.value, prompt: prompt.value.trim(),
    params: { ...rest, input_references: references.value.length ? references.value.map((r)=>({type:'image_url',image_url:{url:r.dataUrl}})) : undefined,
      provider: providerChoice.value ? { only: [providerChoice.value] } : undefined },
  }
  try {
    if (stream) {
      const token = localStorage.getItem('access_token')
      const resp = await fetch('/api/openrouter/images/stream', { method:'POST', headers:{'Content-Type':'application/json', Authorization:`Bearer ${token}`}, body: JSON.stringify(body), credentials:'include' })
      const reader = resp.body!.getReader(); const dec = new TextDecoder(); let buf=''
      for(;;){ const {done,value} = await reader.read(); if(done) break
        buf += dec.decode(value,{stream:true})
        for (const line of buf.split('\n')) { const t=line.trim(); if(!t.startsWith('data:')) continue
          const p=t.slice(5).trim(); if(p==='[DONE]') break
          try{ const ev=JSON.parse(p)
            if(ev.type==='image_generation.completed'&&ev.b64_json){ currentImages.value=[{b64_json:ev.b64_json,media_type:ev.media_type}]; if(ev.usage) usageText.value=`cost: $${ev.usage.cost??'?'}`
              /* 流式完成也不自动入库，需用户逐张点击「入库」 */ }
            else if(ev.type==='error') throw new Error(ev.error?.message||'流式失败')
          }catch(e){ if(e instanceof Error && e.message!=='流式失败') continue; else throw e } }
      }
    } else {
      const res = await orApi.generate(body)
      currentImages.value = res.data
      if (res.usage) usageText.value = `cost: $${res.usage.cost ?? '?'}`
      /* 生成结果默认不入库，需用户逐张点击「入库」 */
    }
  } catch (e: any) { error.value = e.response?.data?.detail || e.message; ElMessage.error(error.value) }
  finally { generating.value = false }
}
async function saveImage(img: any, i: number) {
  await dl({ b64: img.b64_json, mediaType: img.media_type, suggestedName: `or-${Date.now()}-${i}.png` })
}
async function openStock(img: any) {
  stockImg.value = img
  stockTags.value = ''
  // 每次打开都把默认库「上传素材」作为预选（若存在）
  const hit = folders.value.find((f: any) => f.path === '上传素材' || f.name === '上传素材')
  stockFolder.value = hit ? hit.id : (folders.value[0]?.id || '')
  stockOpen.value = true
}
async function confirmStock() {
  if (!stockImg.value) return
  stocking.value = true
  try {
    await api.post('/api/assets/from-generation', {
      b64: stockImg.value.b64_json,
      mime: stockImg.value.media_type || 'image/png',
      folder_id: stockFolder.value || null, // 空则后端默认归入「上传素材」
      tags: stockTags.value.split(',').map((s) => s.trim()).filter(Boolean),
      prompt: prompt.value.trim(),
    })
    ElMessage.success('已存入素材库')
    stockOpen.value = false
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '入库失败') }
  finally { stocking.value = false }
}
onMounted(loadModels)
</script>
<style scoped>
.gen{max-width:860px;margin:0 auto;padding:16px}.topbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.field{margin:12px 0}.kv{color:#888;font-size:12px}.refs{display:flex;gap:8px;flex-wrap:wrap}.ref{position:relative;width:96px;height:96px}.ref .el-image{width:100%;height:100%}
.result-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}.result-item .el-image{width:100%;height:220px}
.hint{color:#888;font-size:12px;margin-top:4px}
</style>
