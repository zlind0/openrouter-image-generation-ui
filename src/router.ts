import { createRouter, createWebHashHistory } from 'vue-router'
import Login from './views/Login.vue'
import Generate from './views/Generate.vue'
import Library from './views/Library.vue'
import Admin from './views/Admin.vue'
import { getToken } from './api/client'

const routes = [
  { path: '/', redirect: '/generate' },
  { path: '/login', component: Login },
  { path: '/generate', component: Generate },
  { path: '/library', component: Library },
  { path: '/admin', component: Admin },
]

export const router = createRouter({ history: createWebHashHistory(), routes })

router.beforeEach((to) => {
  if (to.path !== '/login' && !getToken()) return '/login'
  return true
})
