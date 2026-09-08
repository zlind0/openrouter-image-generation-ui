# OpenRouter 图像生成客户端

Electron + Vue 3 + Vite 实现的 OpenRouter Image API 客户端。

API 依据：`GET /api/v1/images/models`、`GET /api/v1/images/models/{author}/{slug}/endpoints`、`POST /api/v1/images`（支持 `stream: true` SSE）。

## 开发

```bash
npm install
npm run electron:dev   # Vite(5173) + Electron 联调
```

## 构建

```bash
npm run build
```

## 功能

- 顶部设置界面填写并保存 `sk-or-...` API Key（localStorage）
- 从 OpenRouter 读取全部图像模型（`supported_parameters` 能力描述符：enum/range/boolean）
- 选中模型后拉取端点级精确参数并提供默认值：
  - enum（resolution/aspect_ratio/quality/output_format/background）默认取保守值、可选"不发送"
  - n 默认 1、output_compression 默认 80、seed 留空随机、size 留空、stream 默认关
- 参考图：文件选择（Electron 原生 dialog / Web fallback）、拖拽、prompt 输入框及全局剪贴板 Ctrl/Cmd+V 粘贴、图片 URL 添加
- 生成结果展示、保存到本地、作为参考图二次编辑；流式预览（partial_image 事件）
- Provider 路由选择（only），显示各端点价格与透传参数
