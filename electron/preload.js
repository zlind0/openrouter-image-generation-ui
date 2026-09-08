const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  pickImages: () => ipcRenderer.invoke('dialog:pick-images'),
  saveImage: (payload) => ipcRenderer.invoke('dialog:save-image', payload),
})
