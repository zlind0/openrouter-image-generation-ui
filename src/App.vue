<template>
  <div class="app">
    <div class="topbar" v-if="authed">
      <strong>OR Image Web</strong>
      <router-link to="/generate">图片生成</router-link>
      <router-link to="/library">素材管理</router-link>
      <router-link to="/admin" v-if="me?.is_admin">管理</router-link>
      <div class="spacer"></div>
      <span>{{ me?.username }}</span>
      <el-button size="small" @click="logout">退出</el-button>
    </div>
    <router-view />
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { api, getToken, setToken } from './api/client'

const router = useRouter()
const authed = computed(() => !!getToken())
const me = computed(() => { try { return JSON.parse(localStorage.getItem('me') || 'null') } catch { return null } })

async function logout() {
  try { await api.post('/api/auth/logout') } catch {}
  setToken(''); localStorage.removeItem('me'); router.push('/login')
}
</script>
<style>
.topbar{display:flex;gap:12px;align-items:center;padding:10px 16px;border-bottom:1px solid #eee}
.spacer{flex:1}
</style>
