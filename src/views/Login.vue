<template>
  <div style="max-width:420px;margin:80px auto">
    <h2>登录</h2>
    <el-form @submit.prevent="doLogin">
      <el-form-item label="用户名"><el-input v-model="u" /></el-form-item>
      <el-form-item label="密码"><el-input v-model="p" type="password" show-password @keyup.enter="doLogin" /></el-form-item>
      <el-button type="primary" @click="doLogin" :loading="loading" style="width:100%">登录</el-button>
    </el-form>
    <p style="color:#888;margin-top:12px">账号由管理员分配。首个管理员由服务器环境变量创建。</p>
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, setToken } from '../api/client'

const u = ref('')
const p = ref('')
const loading = ref(false)
const router = useRouter()

async function doLogin() {
  loading.value = true
  try {
    const r = await api.post('/api/auth/login', { username: u.value.trim(), password: p.value })
    setToken(r.data.access_token)
    localStorage.setItem('me', JSON.stringify(r.data.user))
    router.push('/generate')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>
