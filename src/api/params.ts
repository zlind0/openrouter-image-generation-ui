import type { CapabilityDescriptor } from '../api/types'

export interface ParamField {
  key: string
  label: string
  kind: 'enum' | 'range' | 'boolean' | 'number' | 'text'
  values?: string[]
  min?: number
  max?: number
  defaultValue: unknown
  hint: string
}

/**
 * 为每个支持的参数生成表单字段 + 默认值。
 * 默认值策略：enum 取中间偏保守值（quality→auto/medium、format→png、ratio→1:1 等），
 * range 取 min，n=1，compression=80，其余留空表示不发送。
 */
export function buildParamFields(supported: Record<string, CapabilityDescriptor>): ParamField[] {
  const fields: ParamField[] = []
  const get = (k: string) => supported[k]
  if (!supported) return fields

  const enumDefaults: Record<string, string> = {
    quality: 'auto',
    output_format: 'png',
    background: 'auto',
    aspect_ratio: '1:1',
    resolution: '1K',
  }

  const pushEnum = (key: string, label: string, hint: string, allowEmpty = true) => {
    const cap = get(key)
    if (!cap || cap.type !== 'enum') return
    fields.push({
      key,
      label,
      kind: 'enum',
      values: cap.values,
      defaultValue: enumDefaults[key] && cap.values.includes(enumDefaults[key]) ? enumDefaults[key] : allowEmpty ? '' : cap.values[0],
      hint,
    })
  }

  pushEnum('resolution', 'Resolution', '输出分辨率档位')
  pushEnum('aspect_ratio', 'Aspect Ratio', '宽高比，auto 由服务端决定')
  pushEnum('quality', 'Quality', '渲染质量')
  pushEnum('output_format', 'Output Format', '返回图片编码')
  pushEnum('background', 'Background', 'transparent 需要 png/webp')

  const n = get('n')
  if (n) {
    if (n.type === 'range') fields.push({ key: 'n', label: 'N（张数）', kind: 'range', min: n.min, max: Math.min(n.max, 10), defaultValue: 1, hint: '1-10，部分服务端只支持 1' })
    else fields.push({ key: 'n', label: 'N（张数）', kind: 'number', min: 1, max: 10, defaultValue: 1, hint: '1-10，部分服务端只支持 1' })
  }
  const comp = get('output_compression')
  if (comp) {
    if (comp.type === 'range') fields.push({ key: 'output_compression', label: 'Output Compression', kind: 'range', min: comp.min, max: comp.max, defaultValue: 80, hint: '仅 webp/jpeg 有效' })
    else fields.push({ key: 'output_compression', label: 'Output Compression', kind: 'number', min: 0, max: 100, defaultValue: 80, hint: '仅 webp/jpeg 有效' })
  }
  const seed = get('seed')
  if (seed) {
    fields.push({ key: 'seed', label: 'Seed', kind: 'number', defaultValue: undefined, hint: '留空为随机；填整数可复现' })
  }
  const size = get('size')
  if (size) {
    fields.push({ key: 'size', label: 'Size 快捷', kind: 'text', defaultValue: '', hint: '如 2K 或 2048x2048；与 resolution/aspect_ratio 冲突会 400' })
  }
  // stream 为 boolean 型能力位：存在即支持
  if (get('stream')) {
    fields.push({ key: 'stream', label: 'Stream 流式', kind: 'boolean', defaultValue: false, hint: '仅部分端点支持，不支持会被忽略' })
  }
  return fields
}

/** 清洗参数：空字符串/undefined 不发送；数字字符串转数字 */
export function cleanParams(values: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(values)) {
    if (v === '' || v === undefined || v === null) continue
    if (k === 'n' || k === 'output_compression' || k === 'seed') {
      const num = typeof v === 'string' ? (v.trim() === '' ? undefined : Number(v)) : (v as number)
      if (num === undefined || Number.isNaN(num)) continue
      out[k] = num
    } else {
      out[k] = v
    }
  }
  return out
}
