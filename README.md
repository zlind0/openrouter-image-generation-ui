# OpenRouter 图像生成 · 网页版（服务端）

Tauri 桌面端已移除（`server` 分支），改为 `FastAPI` 后端 + `Vue3` 前端同源部署。

## 架构

- 前端：`src/`（Vue3 + Element Plus + vue-router），`npm run build` 产出 `dist/`，生产由 FastAPI 同源托管。
- 后端：`backend/app/`（FastAPI）。Key 永不落地前端，所有 OpenRouter 调用经 `/api/openrouter/*` 服务端代理。
- 数据：PostgreSQL（compose）/ SQLite（本地开发），文件存 `DATA_DIR` 本地磁盘。

## 本地开发

```bash
cp backend/.env.example .env   # 填 APP_MASTER_KEY(openssl rand -base64 32) / JWT_SECRET(openssl rand -hex 32) / ADMIN_PASSWORD
pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --port 8000
npm install && npm run dev      # 5173，/api 自动代理到 8000
```

首启会用 `ADMIN_USERNAME/ADMIN_PASSWORD` 创建唯一管理员，登录后请在「管理」页配置 OpenRouter Key（AES-256-GCM 加密存储）并分配普通用户。

## 服务器部署

```bash
# .env 填好 DOMAIN 等，Caddyfile 中的 {$DOMAIN} 替换为真实域名
docker compose up -d --build
```

Caddy 自动签发 HTTPS，反代 `api:8000`。

## 关键特性

- **鉴权**：Argon2id 密码哈希；access JWT(15min)+refresh旋转(HttpOnly Cookie)；单管理员约束；普通用户仅管理自己上传的素材。
- **Key加密**：`APP_MASTER_KEY` 仅来自环境变量；DB 只存 `AES-256-GCM` 密文+nonce+指纹；前端仅见掩码；解密只在服务端内存中转发瞬间发生。
- **素材库**：文件夹树、按文件夹上传（相对路径自动建树）、tag（AND/OR）、EXIF（机身/镜头/ISO…）+文件名/上传者筛选。
- **AVIF向后兼容**：上传原样保存 + 预生成 JPEG 兜底(4:2:0)+WebP缩略图；服务端按 `Accept`/`User-Agent`（Firefox 等）或 `?compat=1` 自动返回 JPEG，响应头 `X-Served-Fallback: avif-to-jpeg`。
- **图床**：`POST /api/assets/{id}/shares` 生成 `/s/{token}` 公开链接（`<img src>` 可直接引用），每次访问记 IP/UA 与计数，`GET /api/shares/{id}/stats` 查看，`DELETE /api/shares/{id}` 撤销（撤销后 404）。
