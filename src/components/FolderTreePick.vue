<template>
  <!-- 和左侧文件夹树同一样式的树形选择器，用于弹窗里选位置/目标文件夹 -->
  <div class="pick-tree">
    <div class="exp-row" :class="{ active: modelValue === '' }" @click="$emit('update:modelValue', '')" title="顶级目录">
      <span class="exp-caret"></span>
      <el-icon class="exp-folder exp-all-icon"><Files /></el-icon>
      <span class="exp-name">顶级目录</span>
    </div>
    <div
      v-for="n in flat"
      :key="n.id"
      class="exp-row"
      :class="{ active: modelValue === n.id }"
      :style="{ paddingLeft: 8 + n.depth * 18 + 'px' }"
      :title="n.path"
      @click="$emit('update:modelValue', n.id)"
    >
      <span class="exp-caret" @click.stop="toggle(n)">
        <el-icon v-if="n.hasChildren"><CaretBottom v-if="!collapsed.has(n.id)" /><CaretRight v-else /></el-icon>
      </span>
      <el-icon class="exp-folder"><FolderOpened v-if="!collapsed.has(n.id)" /><Folder v-else /></el-icon>
      <span class="exp-name">{{ n.name }}</span>
      <span v-if="showCounts && n.subtree_count" class="exp-count">{{ n.subtree_count }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { CaretBottom, CaretRight, Files, Folder, FolderOpened } from '@element-plus/icons-vue'

const props = withDefaults(
  defineProps<{ modelValue: string; folders: any[]; showCounts?: boolean }>(),
  { showCounts: true },
)
defineEmits(['update:modelValue'])

const collapsed = ref<Set<string>>(new Set())
const flat = computed(() => {
  const byParent = new Map<string, any[]>()
  for (const f of props.folders) {
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
function toggle(n: any) {
  if (collapsed.value.has(n.id)) collapsed.value.delete(n.id)
  else collapsed.value.add(n.id)
}
</script>

<style scoped>
.pick-tree {
  max-height: 260px; overflow-y: auto; padding: 6px;
  border-radius: 8px;
  background: linear-gradient(to bottom, #1a1d21, #26292f 45%);
  border: 1px solid #101215;
  box-shadow: inset 0 1px 4px rgba(0, 0, 0, 0.55), 0 1px 0 rgba(255, 255, 255, 0.12);
}
</style>
