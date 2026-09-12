<template>
  <div style="max-width:760px;margin:0 auto;padding:16px">
    <h2>管理（仅管理员）</h2>
    <el-card style="margin-bottom:16px"><template #header>OpenRouter Key（AES-256-GCM 加密存储）</template>
      <p>状态：{{ keyStatus.configured ? `已配置 ${keyStatus.masked}（指纹 ${keyStatus.fingerprint}）` : '未配置' }}</p>
      <el-input v-model="newKey" type="password" show-password placeholder="sk-or-..." style="margin:8px 0" />
      <el-button type="primary" @click="saveKey">保存/轮换</el-button>
    </el-card>
    <el-card><template #header>用户管理</template>
      <div style="display:flex;gap:8px;margin-bottom:8px">
        <el-input v-model="nu" placeholder="新用户名" style="width:160px" />
        <el-input v-model="np" placeholder="初始密码" style="width:160px" />
        <el-button @click="addUser">创建用户</el-button>
      </div>
      <el-table :data="users" style="width:100%">
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="is_admin" label="管理员"><template #default="{row}">{{ row.is_admin?'是':'否' }}</template></el-table-column>
        <el-table-column prop="is_active" label="启用"><template #default="{row}">{{ row.is_active?'是':'否' }}</template></el-table-column>
        <el-table-column label="操作"><template #default="{row}">
          <el-button size="small" @click="resetPw(row)" :disabled="row.is_admin">重置密码</el-button>
          <el-button size="small" @click="toggle(row)" :disabled="row.is_admin">{{ row.is_active?'停用':'启用' }}</el-button>
          <el-button size="small" type="danger" @click="del(row)" :disabled="row.is_admin">删除</el-button>
        </template></el-table-column>
      </el-table>
    </el-card>
  </div>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/client'

const users = ref<any[]>([])
const keyStatus = ref<any>({})
const newKey = ref('')
const nu = ref(''), np = ref('')

async function load() {
  try {
    users.value = (await api.get('/api/admin/users')).data
    keyStatus.value = (await api.get('/api/admin/settings/openrouter-key')).data
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '仅管理员可访问') }
}
async function saveKey() {
  await api.put('/api/admin/settings/openrouter-key', { api_key: newKey.value.trim() })
  newKey.value = ''; ElMessage.success('已保存'); load()
}
async function addUser() {
  await api.post('/api/admin/users', { username: nu.value.trim(), password: np.value })
  nu.value = ''; np.value = ''; load()
}
async function resetPw(row: any) {
  const { value } = await ElMessageBox.prompt(`重置 ${row.username} 的密码`, '重置密码')
  if (value) { await api.patch(`/api/admin/users/${row.id}`, { password: value }); ElMessage.success('已重置') }
}
async function toggle(row: any) { await api.patch(`/api/admin/users/${row.id}`, { is_active: !row.is_active }); load() }
async function del(row: any) {
  await ElMessageBox.confirm(`删除 ${row.username}？其上传的素材保留，归属不变。`, '确认', { type: 'warning' })
  await api.delete(`/api/admin/users/${row.id}`); load()
}
onMounted(load)
</script>
