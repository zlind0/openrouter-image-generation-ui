import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Pure web app: frontend served by backend static mount in prod,
// dev proxies /api to FastAPI (uvicorn localhost:8000)
export default defineConfig({
  plugins: [vue()],
  base: './',
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/s': 'http://127.0.0.1:8000',
    },
  },
  build: { outDir: 'dist' },
})
