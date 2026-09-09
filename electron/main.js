const { app, BrowserWindow, ipcMain, dialog, Menu } = require('electron')
const path = require('path')
const fs = require('fs')

let mainWindow = null
const isMac = process.platform === 'darwin'

function createWindow() {
  // 去掉原生菜单（File/Edit/View... 很丑）
  Menu.setApplicationMenu(null)
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 1024,
    minHeight: 700,
    title: 'OpenRouter ImageGen UI',
    icon: path.join(__dirname, '../build/icon.png'),
    backgroundColor: '#161c22',
    autoHideMenuBar: true,
    // macOS：保留红绿灯，隐藏原生白色标题栏，红绿灯嵌进自绘顶栏左侧
    // Windows/Linux：frameless，右上角用自绘最小化/最大化/关闭
    frame: isMac,
    ...(isMac
      ? { titleBarStyle: 'hidden', trafficLightPosition: { x: 12, y: 12 } }
      : { titleBarStyle: 'hidden' }),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  const devUrl = process.env.VITE_DEV_SERVER_URL
  if (devUrl) {
    mainWindow.loadURL(devUrl)
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  // frameless 下同步最大化状态，给自绘按钮切换图标
  const sendMaxState = () => {
    if (mainWindow) mainWindow.webContents.send('window:max-state', mainWindow.isMaximized())
  }
  mainWindow.on('maximize', sendMaxState)
  mainWindow.on('unmaximize', sendMaxState)
}

// 自绘标题栏按钮（仅 Windows/Linux frameless 用，macOS 用红绿灯）
ipcMain.on('window:minimize', () => mainWindow?.minimize())
ipcMain.on('window:toggle-maximize', () => {
  if (!mainWindow) return
  if (mainWindow.isMaximized()) mainWindow.unmaximize()
  else mainWindow.maximize()
})
ipcMain.on('window:close', () => mainWindow?.close())
ipcMain.handle('window:is-maximized', () => !!mainWindow?.isMaximized())

app.whenReady().then(() => {
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

// 选择参考图片（返回 dataURL 数组）
ipcMain.handle('dialog:pick-images', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: '选择参考图片',
    properties: ['openFile', 'multiSelections'],
    filters: [{ name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'svg'] }],
  })
  if (result.canceled) return []
  return result.filePaths.map((p) => {
    const buf = fs.readFileSync(p)
    const ext = path.extname(p).toLowerCase()
    const mime =
      ext === '.jpg' || ext === '.jpeg'
        ? 'image/jpeg'
        : ext === '.webp'
          ? 'image/webp'
          : ext === '.gif'
            ? 'image/gif'
            : ext === '.bmp'
              ? 'image/bmp'
              : ext === '.svg'
                ? 'image/svg+xml'
                : 'image/png'
    return { name: path.basename(p), dataUrl: `data:${mime};base64,${buf.toString('base64')}` }
  })
})

// 保存生成的图片
ipcMain.handle('dialog:save-image', async (_event, { b64, mediaType, suggestedName }) => {
  const ext = mediaType === 'image/jpeg' ? 'jpg' : mediaType === 'image/webp' ? 'webp' : mediaType === 'image/svg+xml' ? 'svg' : 'png'
  const result = await dialog.showSaveDialog(mainWindow, {
    title: '保存图片',
    defaultPath: suggestedName || `openrouter-image-${Date.now()}.${ext}`,
    filters: [{ name: 'Images', extensions: [ext] }],
  })
  if (result.canceled || !result.filePath) return { saved: false }
  const buf = mediaType === 'image/svg+xml' ? Buffer.from(b64, 'base64') : Buffer.from(b64, 'base64')
  fs.writeFileSync(result.filePath, buf)
  return { saved: true, path: result.filePath }
})
