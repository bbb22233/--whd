# Telegram Mini App + Next.js 调试笔记

## 背景

Telegram Mini App 使用 Telegram 客户端的 WebView 渲染，与常规浏览器有显著差异。Next.js 的 SSR + RSC (React Server Components) 在此环境下容易出问题。整个项目在 Docker 容器内运行（无端口映射到宿主机），通过 Cloudflared tunnel 暴露 HTTPS 访问。

## 常见错误消息与排查

### 错误消息：`Failed to execute 'fetch' on 'Window'`

**完整原文**: `Failed to execute 'fetch' on 'Window': Failed to read the 'headers' property from 'RequestInit': String contains non ISO-8859-1 code point`

**定位**: 在 Telegram WebView 控制台看到此报错（而非浏览器），说明 Telegram 对 header 编码比标准浏览器更严格。

**根本原因**: `apiFetch()` 函数自动从 Telegram WebApp 的 `initDataUnsafe.user` 提取用户信息（`id`, `first_name`, `last_name`, `username`）拼接成自定义 headers（如 `x-display-name`、`x-user-id`），传递给后端。当用户在 Telegram 上设置了中文/日文/emoji 等非 Latin-1 字符的昵称时，header 值就会触发此错误——HTTP 协议要求 header 值只能包含 ISO-8859-1 字符（0x00-0xFF）。

**修复**: 对每个自定义 header 值做 Latin-1 过滤：
```typescript
function safeHeaderValue(value: string): string {
  return value.replace(/[^\x00-\xFF]/g, '?');
}
```

在 `buildViewerIdentityHeaders()` 内对每个 header 值调用此函数后再传给 `fetch()`。

### 错误消息：`Failed to fetch`（无更多细节）

**可能原因**（按排查顺序）:
1. 上述 header 编码问题（最常见的 Telegram WebView 特有问题）
2. 后端服务未启动或端口不对（用 `curl :3012/api/rooms` 验证）
3. Cloudflared tunnel 断开或 URL 变更
4. CORS 或网络隔离问题

### 错误消息：Mini App 空白页面（浏览器正常渲染）

**可能原因**:
1. **RSC 流式注入** — Next.js dev server 用 `self.__next_f.push` 做 RSC 流式注入，Telegram WebView 可能不支持
2. **HMR websocket** — `ws://` 协议在 HTTPS 环境下被 Telegram WebView 阻止混合内容
3. **Telegram JS SDK 未加载** — 缺少 `telegram-web-app.js` 脚本

**修复方案**（按推荐顺序）:
1. **Telegram JS SDK** — 在 `layout.tsx` 的 `<head>` 内添加 `<script src="https://telegram.org/js/telegram-web-app.js">`
2. **client-only 渲染** — 将首页从 async Server Component 改为 `'use client'`，API 请求移到 `useEffect` 内
3. **生产构建** — `next build && next start` 替代 dev server（去掉 HMR websocket）

## Docker 环境的特殊注意事项

当项目跑在 Docker 容器内（如 `hermes-dragon`）时：

- **无 `kill`/`ps`/`fuser`** — 容器内缺少这些工具，用 `docker exec` 从宿主机操作进程
- **端口映射** — 如果容器没有端口映射到宿主机（`-p` 参数），服务只能容器内互相访问；外部通过 Cloudflared tunnel 暴露
- **重启容器后** — 所有手动启动的进程（非 Dockerfile CMD）都会丢失，需重新启动完整服务链
- **进程管理** — 用 `pkill -f "tsx.*bot"` 和 `pkill -f "next.*dev"` 从容器内关停进程
- **`source` 不可用** — 容器 shell 可能不支持 `source` 命令，用 `.` 代替：
  ✅ `. /workspace/telegram-poker/.env.local`
  ❌ `source /workspace/telegram-poker/.env.local`

## 测试配置

### 网络拓扑

```
Telegram 客户端 → Cloudflared Tunnel (HTTPS) → Next.js (:3030)
                                                → Express (:3012)
                                                → Telegram Bot
```

### 启动顺序（容器重启后完整链）

1. Next.js dev server:
   ```
   cd /workspace/telegram-poker/apps/webapp && npx next dev --port 3030
   ```
2. Express server:
   ```
   cd /workspace/telegram-poker/apps/server && npx tsx src/index.ts
   ```
3. Cloudflared tunnel:
   ```
   /tmp/cloudflared tunnel --url http://localhost:3030
   ```
4. 从 tunnel 日志获取新 URL（每次重启不同）
5. 更新 `.env.local`:
   ```
   sed -i "s|TELEGRAM_WEBAPP_URL=.*|TELEGRAM_WEBAPP_URL=<new-url>|" /workspace/telegram-poker/.env.local
   ```
6. 重启 bot（加载新环境变量）:
   ```
   pkill -f "tsx.*bot"; sleep 1
   . /workspace/telegram-poker/.env.local
   cd /workspace/telegram-poker && nohup npx tsx apps/bot/src/index.ts > /tmp/bot.log 2>&1 &
   ```
7. 验证:
   ```
   curl -so /dev/null -w '%{http_code}' <tunnel-url>     # 应返回 200
   curl -s <tunnel-url> | grep telegram-web-app           # 应找到 JS SDK
   ```

### 注意

- Cloudflared quick tunnel 每次重启获取随机 URL，不能用固定的 ngrok 域名
- 每次新 tunnel URL 都必须同步更新 `.env.local` 的 `TELEGRAM_WEBAPP_URL` 并重启 bot
- bot 读的是启动时的进程环境变量，不是运行时动态读取
- apt-get 安装的 cloudflared 如果不在容器内可以用；否则用下载的 `/tmp/cloudflared` 二进制
