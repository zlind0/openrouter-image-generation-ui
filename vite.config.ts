import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Tauri: 固定端口供 devUrl，监听 src-tauri 变动不触发重载由 CLI 接管
export default defineConfig({
  plugins: [vue()],
  base: './',
  clearScreen: false,
  server: { port: 5173, strictPort: true },
  build: { outDir: 'dist' },
})
