const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  pickImages: () => ipcRenderer.invoke('dialog:pick-images'),
  saveImage: (payload) => ipcRenderer.invoke('dialog:save-image', payload),
  platform: process.platform,
  minimize: () => ipcRenderer.send('window:minimize'),
  toggleMaximize: () => ipcRenderer.send('window:toggle-maximize'),
  close: () => ipcRenderer.send('window:close'),
  isMaximized: () => ipcRenderer.invoke('window:is-maximized'),
  onMaxState: (cb) => ipcRenderer.on('window:max-state', (_e, v) => cb(v)),
  setProxy: (cfg) => ipcRenderer.invoke('proxy:set', cfg),
  fetchImageUrl: (url) => ipcRenderer.invoke('image:fetch-url', url),
})
