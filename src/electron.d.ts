/// <reference types="vite/client" />

interface ElectronAPI {
  pickImages: () => Promise<Array<{ name: string; dataUrl: string }>>
  saveImage: (payload: { b64: string; mediaType?: string; suggestedName?: string }) => Promise<{ saved: boolean; path?: string }>
  platform?: NodeJS.Platform
  minimize?: () => void
  toggleMaximize?: () => void
  close?: () => void
  isMaximized?: () => Promise<boolean>
  onMaxState?: (cb: (maxed: boolean) => void) => void
  setProxy?: (cfg: ProxyConfig) => Promise<{ ok: boolean; mode?: string; proxyRules?: string }>
  fetchImageUrl?: (url: string) => Promise<{ dataUrl: string; contentType?: string }>
}

export interface ProxyConfig {
  enabled: boolean
  type: 'http' | 'https' | 'socks5'
  url: string
  username: string
  password: string
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}

export {}
