//! Tauri 后端：OpenRouter API（经 reqwest，支持 http/https/socks5 代理）、
//! 图片拉取、原生文件对话框、自绘标题栏窗口控制。
//! 网络全部走 Rust，WebView 只负责展示，因此代理对 API/参考图/余额全量生效。

use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tauri::{Emitter, WebviewUrl, WebviewWindowBuilder};

const REFERRER: &str = "https://localhost/openrouter-image-client";
const APP_TITLE: &str = "OpenRouter ImageGen UI";
const IMAGE_MAX_BYTES: usize = 15 * 1024 * 1024;

/* ---------------- 通用 ---------------- */

#[derive(Debug, Clone, Deserialize)]
struct ProxyConfig {
    enabled: bool,
    #[serde(rename = "type")]
    proxy_type: String, // http | https | socks5（前端传 proxyType，Tauri 自动转 snake_case）
    url: String,
    username: String,
    password: String,
}

fn trim_base(base_url: &str) -> String {
    base_url.trim().trim_end_matches('/').to_string()
}

/// 用户填的 url 归一化成 host:port（去掉 scheme 和末尾 /）
fn normalize_hostport(url: &str) -> String {
    let u = url.trim();
    let u = u.split("://").last().unwrap_or(u);
    u.trim_end_matches('/').to_string()
}

fn build_client(proxy: &Option<ProxyConfig>) -> Result<reqwest::Client, String> {
    let mut b = reqwest::Client::builder().timeout(Duration::from_secs(60));
    match proxy {
        Some(p) if p.enabled && !p.url.trim().is_empty() => {
            let hp = normalize_hostport(&p.url);
            if !hp.contains(':') {
                return Err("代理地址无效，应为 host:port，可带 scheme".into());
            }
            // socks5h：DNS 也走代理；https 经 http(s) 代理用 CONNECT
            let scheme = match p.proxy_type.as_str() {
                "socks5" => "socks5h",
                "https" => "https",
                _ => "http",
            };
            let proxy_url = format!("{scheme}://{hp}");
            let mut px =
                reqwest::Proxy::all(&proxy_url).map_err(|e| format!("代理地址无效：{e}"))?;
            if !p.username.is_empty() {
                px = px.basic_auth(&p.username, &p.password);
            }
            b = b.proxy(px);
        }
        _ => {
            b = b.no_proxy();
        }
    }
    b.build().map_err(|e| e.to_string())
}

fn api_headers(api_key: &str) -> reqwest::header::HeaderMap {
    let mut h = reqwest::header::HeaderMap::new();
    h.insert(
        reqwest::header::AUTHORIZATION,
        format!("Bearer {api_key}").parse().unwrap(),
    );
    h.insert(
        reqwest::header::CONTENT_TYPE,
        "application/json".parse().unwrap(),
    );
    h.insert("HTTP-Referer", REFERRER.parse().unwrap());
    h.insert("X-Title", APP_TITLE.parse().unwrap());
    h
}

fn or_err(v: &serde_json::Value, status: u16) -> String {
    if let Some(e) = v.get("error") {
        let code = e
            .get("code")
            .map(|c| {
                if c.is_string() {
                    c.as_str().unwrap_or("").to_string()
                } else {
                    c.to_string()
                }
            })
            .unwrap_or_default();
        let msg = e
            .get("message")
            .and_then(|m| m.as_str())
            .unwrap_or("请求失败");
        return format!("Error {code}: {msg}").trim().to_string();
    }
    format!("请求失败 ({status})")
}

async fn read_json(res: reqwest::Response) -> Result<(u16, serde_json::Value), String> {
    let status = res.status().as_u16();
    let text = res.text().await.map_err(|e| e.to_string())?;
    let v: serde_json::Value =
        serde_json::from_str(&text).unwrap_or(serde_json::Value::String(text));
    Ok((status, v))
}

/* ---------------- OpenRouter API ---------------- */

#[tauri::command]
async fn or_models(
    api_key: String,
    base_url: String,
    proxy: Option<ProxyConfig>,
) -> Result<serde_json::Value, String> {
    let client = build_client(&proxy)?;
    let url = format!("{}/images/models", trim_base(&base_url));
    let res = client
        .get(&url)
        .headers(api_headers(&api_key))
        .send()
        .await
        .map_err(|e| e.to_string())?;
    let (status, v) = read_json(res).await?;
    if !(200..300).contains(&status) {
        return Err(or_err(&v, status));
    }
    Ok(v)
}

#[tauri::command]
async fn or_endpoints(
    api_key: String,
    base_url: String,
    model_id: String,
    proxy: Option<ProxyConfig>,
) -> Result<serde_json::Value, String> {
    let mut parts = model_id.splitn(2, '/');
    let author = parts.next().unwrap_or("");
    let slug = parts.next().unwrap_or("");
    let client = build_client(&proxy)?;
    let url = format!(
        "{}/images/models/{}/{}/endpoints",
        trim_base(&base_url),
        author,
        slug
    );
    let res = client
        .get(&url)
        .headers(api_headers(&api_key))
        .send()
        .await
        .map_err(|e| e.to_string())?;
    let (status, v) = read_json(res).await?;
    if !(200..300).contains(&status) {
        return Err(or_err(&v, status));
    }
    Ok(v)
}

#[tauri::command]
async fn or_generate(
    api_key: String,
    base_url: String,
    body: serde_json::Value,
    proxy: Option<ProxyConfig>,
) -> Result<serde_json::Value, String> {
    let client = build_client(&proxy)?;
    let url = format!("{}/images", trim_base(&base_url));
    let res = client
        .post(&url)
        .headers(api_headers(&api_key))
        .json(&body)
        .send()
        .await
        .map_err(|e| e.to_string())?;
    let (status, v) = read_json(res).await?;
    if !(200..300).contains(&status) {
        return Err(or_err(&v, status));
    }
    Ok(v)
}

/// SSE 流式生成：partial/completed/error 事件经 Channel 逐条推给前端
#[tauri::command]
async fn or_generate_stream(
    api_key: String,
    base_url: String,
    mut body: serde_json::Value,
    proxy: Option<ProxyConfig>,
    on_event: tauri::ipc::Channel<serde_json::Value>,
) -> Result<(), String> {
    if let Some(obj) = body.as_object_mut() {
        obj.insert("stream".into(), serde_json::Value::Bool(true));
    }
    let client = build_client(&proxy)?;
    let url = format!("{}/images", trim_base(&base_url));
    let res = client
        .post(&url)
        .headers(api_headers(&api_key))
        .json(&body)
        .send()
        .await
        .map_err(|e| e.to_string())?;
    if !res.status().is_success() {
        let status = res.status().as_u16();
        let (_, v) = read_json(res).await?;
        return Err(or_err(&v, status));
    }
    let mut res = res;
    let mut buf = String::new();
    loop {
        match res.chunk().await {
            Ok(Some(bytes)) => {
                buf.push_str(&String::from_utf8_lossy(&bytes));
                while let Some(pos) = buf.find('\n') {
                    let line = buf[..pos].trim().to_string();
                    buf = buf[pos + 1..].to_string();
                    let Some(payload) = line.strip_prefix("data:") else {
                        continue;
                    };
                    let p = payload.trim();
                    if p == "[DONE]" {
                        return Ok(());
                    }
                    if let Ok(v) = serde_json::from_str::<serde_json::Value>(p) {
                        on_event.send(v).map_err(|e| e.to_string())?;
                    }
                }
            }
            Ok(None) => break,
            Err(e) => return Err(e.to_string()),
        }
    }
    Ok(())
}

#[tauri::command]
async fn or_key_info(
    api_key: String,
    base_url: String,
    proxy: Option<ProxyConfig>,
) -> Result<serde_json::Value, String> {
    let client = build_client(&proxy)?;
    let url = format!("{}/key", trim_base(&base_url));
    let res = client
        .get(&url)
        .headers(api_headers(&api_key))
        .send()
        .await
        .map_err(|e| e.to_string())?;
    let (status, v) = read_json(res).await?;
    if !(200..300).contains(&status) {
        return Err(or_err(&v, status));
    }
    Ok(v)
}

/* ---------------- 参考图 URL：经本机代理拉取转 dataURL ---------------- */

#[derive(Debug, Clone, Serialize)]
struct FetchedImage {
    #[serde(rename = "dataUrl")]
    data_url: String,
    #[serde(rename = "contentType")]
    content_type: String,
}

#[tauri::command]
async fn fetch_image_url(
    url: String,
    proxy: Option<ProxyConfig>,
) -> Result<FetchedImage, String> {
    let u = url.trim().to_string();
    if !(u.starts_with("http://") || u.starts_with("https://")) {
        return Err("仅支持 http(s) 图片 URL".into());
    }
    let client = build_client(&proxy)?;
    let res = client
        .get(&u)
        .timeout(Duration::from_secs(30))
        .send()
        .await
        .map_err(|e| e.to_string())?;
    if !res.status().is_success() {
        return Err(format!("拉图失败 ({})", res.status().as_u16()));
    }
    let ct = res
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .split(';')
        .next()
        .unwrap_or("")
        .trim()
        .to_lowercase();
    if !ct.is_empty() && !ct.starts_with("image/") {
        return Err(format!("URL 不是图片（{ct}）"));
    }
    let bytes = res.bytes().await.map_err(|e| e.to_string())?;
    if bytes.len() > IMAGE_MAX_BYTES {
        return Err("图片超过 15MB，请压缩后重试".into());
    }
    let mime = if ct.starts_with("image/") {
        ct.clone()
    } else {
        "image/png".to_string()
    };
    Ok(FetchedImage {
        data_url: format!("data:{mime};base64,{}", STANDARD.encode(&bytes)),
        content_type: mime,
    })
}

/* ---------------- 原生文件对话框 ---------------- */

#[derive(Debug, Clone, Serialize)]
struct PickedImage {
    name: String,
    #[serde(rename = "dataUrl")]
    data_url: String,
}

fn mime_of(ext: &str) -> &'static str {
    match ext {
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "gif" => "image/gif",
        "bmp" => "image/bmp",
        "svg" => "image/svg+xml",
        _ => "image/png",
    }
}

#[tauri::command]
fn pick_images() -> Result<Vec<PickedImage>, String> {
    let files = rfd::FileDialog::new()
        .set_title("选择参考图片")
        .add_filter("Images", &["png", "jpg", "jpeg", "webp", "gif", "bmp", "svg"])
        .pick_files()
        .unwrap_or_default();
    let mut out = Vec::new();
    for fh in files {
        let p = fh.as_path().to_owned();
        let bytes = std::fs::read(&p).map_err(|e| e.to_string())?;
        let ext = p
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("")
            .to_lowercase();
        let mime = mime_of(ext.as_str());
        let name = p
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("image")
            .to_string();
        out.push(PickedImage {
            name,
            data_url: format!("data:{mime};base64,{}", STANDARD.encode(&bytes)),
        });
    }
    Ok(out)
}

#[derive(Debug, Clone, Serialize)]
struct SaveResult {
    saved: bool,
    path: Option<String>,
}

#[tauri::command]
fn save_image(
    b64: String,
    media_type: Option<String>,
    suggested_name: Option<String>,
) -> Result<SaveResult, String> {
    let mt = media_type.unwrap_or_default();
    let ext = match mt.as_str() {
        "image/jpeg" => "jpg",
        "image/webp" => "webp",
        "image/svg+xml" => "svg",
        _ => "png",
    };
    let name = suggested_name.unwrap_or_else(|| format!("openrouter-image-{}.{}", now_ms(), ext));
    let Some(path) = rfd::FileDialog::new()
        .set_title("保存图片")
        .set_file_name(&name)
        .add_filter("Images", &[ext])
        .save_file()
    else {
        return Ok(SaveResult {
            saved: false,
            path: None,
        });
    };
    let bytes = STANDARD.decode(b64.trim()).map_err(|e| e.to_string())?;
    std::fs::write(&path, bytes).map_err(|e| e.to_string())?;
    Ok(SaveResult {
        saved: true,
        path: path.to_str().map(|s| s.to_string()),
    })
}

fn now_ms() -> u128 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0)
}

/* ---------------- 自绘标题栏窗口控制 ---------------- */

#[tauri::command]
fn win_minimize(window: tauri::Window) -> Result<(), String> {
    window.minimize().map_err(|e| e.to_string())
}

#[tauri::command]
fn win_toggle_maximize(window: tauri::Window) -> Result<(), String> {
    if window.is_maximized().map_err(|e| e.to_string())? {
        window.unmaximize().map_err(|e| e.to_string())
    } else {
        window.maximize().map_err(|e| e.to_string())
    }
}

#[tauri::command]
fn win_close(window: tauri::Window) -> Result<(), String> {
    window.close().map_err(|e| e.to_string())
}

#[tauri::command]
fn win_is_maximized(window: tauri::Window) -> Result<bool, String> {
    window.is_maximized().map_err(|e| e.to_string())
}

/* ---------------- 入口 ---------------- */

fn main() {
    tauri::Builder::default()
        // frameless 下同步最大化状态，给自绘按钮切换图标
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::Resized(_)) {
                if let Ok(m) = window.is_maximized() {
                    let _ = window.emit("window:max-state", m);
                }
            }
        })
        .setup(|app| {
            let builder = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("OpenRouter ImageGen UI")
                .inner_size(1280.0, 860.0)
                .min_inner_size(1024.0, 700.0)
                // 关掉 Tauri 的文件拖放拦截，否则 Windows 上 HTML5 drop 拿不到文件
                .disable_drag_drop_handler();
            // macOS：保留红绿灯 + 隐藏标题栏；Win/Linux：无边框，自绘右置按钮
            #[cfg(target_os = "macos")]
            let builder = builder
                .decorations(true)
                .title_bar_style(tauri::TitleBarStyle::Overlay);
            #[cfg(not(target_os = "macos"))]
            let builder = builder.decorations(false);
            builder.build()?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            or_models,
            or_endpoints,
            or_generate,
            or_generate_stream,
            or_key_info,
            fetch_image_url,
            pick_images,
            save_image,
            win_minimize,
            win_toggle_maximize,
            win_close,
            win_is_maximized,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
