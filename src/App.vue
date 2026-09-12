<template>
  <div class="app">
    <div class="topbar" v-if="authed">
      <div class="brand"><img class="app-icon" src="/icon.png" alt="logo" /><strong>OR Image Web</strong></div>
      <nav>
        <router-link to="/generate">图片生成</router-link>
        <router-link to="/library">素材管理</router-link>
        <router-link to="/admin" v-if="me?.is_admin">管理</router-link>
      </nav>
      <div class="spacer"></div>
      <span class="me">{{ me?.username }}</span>
      <el-button size="small" @click="logout">退出</el-button>
    </div>
    <router-view />
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { api, authTick, getToken, setToken } from './api/client'

const router = useRouter()
const authed = computed(() => { void authTick.value; return !!getToken() })
const me = computed(() => { void authTick.value; try { return JSON.parse(localStorage.getItem('me') || 'null') } catch { return null } })

async function logout() {
  try { await api.post('/api/auth/logout') } catch {}
  setToken(''); localStorage.removeItem('me'); router.push('/login')
}
</script>
<!-- 顶栏样式由全局拟物主题（style.css）统一提供 -->
