/// <reference types="vite/client" />

interface ElectronAPI {
  pickImages: () => Promise<Array<{ name: string; dataUrl: string }>>
  saveImage: (payload: { b64: string; mediaType?: string; suggestedName?: string }) => Promise<{ saved: boolean; path?: string }>
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}

export {}
