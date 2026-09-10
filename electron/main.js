const { app, BrowserWindow, ipcMain, dialog, Menu, session, net } = require('electron')
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

// ---- 代理：renderer 的 fetch 走 Chromium 网络栈，session 级代理对其生效 ----
let proxyAuth = { username: '', password: '' }
app.on('login', (event, _webContents, _details, authInfo, callback) => {
  if (authInfo.isProxy && proxyAuth.username) {
    event.preventDefault()
    callback(proxyAuth.username, proxyAuth.password)
  }
})

function normalizeHostPort(url) {
  return String(url || '')
    .trim()
    .replace(/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//, '')
    .replace(/\/+$/, '')
}

ipcMain.handle('proxy:set', async (_event, cfg) => {
  const ses = session.defaultSession
  proxyAuth = { username: (cfg && cfg.username) || '', password: (cfg && cfg.password) || '' }
  if (!cfg || !cfg.enabled || !cfg.url || !cfg.url.trim()) {
    await ses.setProxy({ mode: 'direct' })
    return { ok: true, mode: 'direct' }
  }
  const hostport = normalizeHostPort(cfg.url)
  if (!hostport || !hostport.includes(':')) throw new Error('代理地址无效，应为 host:port，可带 scheme')
  const type = cfg.type === 'socks5' ? 'socks5' : cfg.type === 'https' ? 'https' : 'http'
  const proxyRules = `${type}://${hostport}`
  await ses.setProxy({ proxyRules, proxyBypassRules: '<local>' })
  return { ok: true, proxyRules }
})

app.whenReady().then(() => {
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

// 经本机代理拉取图片 URL 转 dataURL：net 走 session 代理（含认证），
// 预览与生成上传都用字节，不依赖 OpenRouter 服务端去抓 URL
ipcMain.handle('image:fetch-url', async (_event, url) => {
  const u = String(url || '').trim()
  if (!/^https?:\/\//i.test(u)) throw new Error('仅支持 http(s) 图片 URL')
  const res = await net.fetch(u, { signal: AbortSignal.timeout(30000) })
  if (!res.ok) throw new Error(`拉图失败 (${res.status})`)
  const ct = (res.headers.get('content-type') || '').split(';')[0].trim().toLowerCase()
  if (ct && !ct.startsWith('image/')) throw new Error(`URL 不是图片（${ct}）`)
  const buf = Buffer.from(await res.arrayBuffer())
  const MAX = 15 * 1024 * 1024
  if (buf.length > MAX) throw new Error('图片超过 15MB，请压缩后重试')
  const mime = ct.startsWith('image/') ? ct : 'image/png'
  return { dataUrl: `data:${mime};base64,${buf.toString('base64')}`, contentType: mime }
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
