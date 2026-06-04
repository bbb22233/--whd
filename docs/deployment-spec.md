# 部署上线方案(三档:本地 / 内网 / 公网)

> 只读部署 spec。基线 `main @ 0657ec4`。本项目当前是**本地工具**设计(全绑 `127.0.0.1`、无鉴权、`API_BASE` 写死),三档逐级加固。
> 架构回顾(见 `target-architecture.md`):Python 算+数据 → FastAPI REST(唯一窗口)→ 静态前端(REST + 文件回退)。

## 0. 现状里阻碍"非本地"部署的写死点(三档都围着这几处改)
| 位置 | 现状 | 影响 |
|---|---|---|
| `backend_py/main.py:210` | uvicorn `host=127.0.0.1, port=8000`(仅 `__main__`) | CLI `--host/--port` 可覆盖,不算硬障碍 |
| `backend_py/main.py:12` | `ALLOWED_ORIGINS` 写死 localhost:4177 | 换域名要改(建议改读环境变量) |
| `server.mjs:62` | `listen(port, "127.0.0.1")` 写死本机 | 非本机访问要改绑定/走反代 |
| `server.mjs:7` | `PORT` 已可用环境变量配 | OK |
| `app.js:1` | `API_BASE = "http://127.0.0.1:8000"` 写死 | **关键**:别人浏览器访问时连不到你的 127.0.0.1 |
| 全 API | **无任何鉴权** | scanner 能触发下载/重算/写盘,公网必须锁 |

**前置(三档通用)**:部署机要能跑 `uv`(Python 产线)、有 `data/clean` + `reports/`(首次需联网 OKX 生成),Node 仅用于前端静态服务(`server.mjs`)。

---

## 档 1 — 本地 / 个人单机(现在就能上)
**适用**:只你自己在本机看。**无需改任何代码。**

```bash
# 0)(首次/刷新数据)生成 data/clean + reports —— 需联网 OKX
uv run python -m backend_py.run_data_pipeline --download-only --days 3650   # 下载
uv run python -m backend_py.run_full_pipeline --skip-download --official --days 3650 --bars "1D,4H,8H,1W"  # 算+写报告

# 1) 起后端 API
uv run uvicorn backend_py.main:app --host 127.0.0.1 --port 8000

# 2) 起前端静态服务(另开一个终端)
node server.mjs              # → http://127.0.0.1:4177
```
浏览器开 `http://127.0.0.1:4177/?instrument=BTC-USDT&bar=1D`。**安全模型成立**(全本机、CORS/Origin 闸已生效)。

---

## 档 2 — 内网 / 自托管(局域网、可信网络内多人看)
**适用**:家里/公司内网,信任访问者,但要让别的机器能打开。

**要改 3 处(建议改成环境变量驱动,而非写死):**

1. **`app.js` 的 `API_BASE` 相对化** —— 最关键。改成同源相对路径,让前端用"访问它的那个主机"去调 API:
   ```js
   // 推荐:前端和 API 走同一个反代/同源时
   const API_BASE = "";   // 同源,fetch("/api/...")
   // 或按部署主机注入:const API_BASE = window.__API_BASE__ ?? "";
   ```
   配套:用一个反代(下面 nginx/caddy)把 `/api/*` 转给 8000、其余给 4177,实现同源。

2. **`server.mjs` 绑定地址** —— 让非本机可达:
   ```js
   const host = process.env.HOST ?? "127.0.0.1";
   server.listen(port, host, () => { ... });   // 内网用 HOST=0.0.0.0
   ```

3. **`main.py` 的 `ALLOWED_ORIGINS`** —— 改读环境变量,纳入内网域名/IP:
   ```python
   import os
   ALLOWED_ORIGINS = [o for o in os.environ.get("ALLOWED_ORIGINS", "http://127.0.0.1:4177,http://localhost:4177").split(",") if o]
   ```

**起服(绑内网网卡):**
```bash
uv run uvicorn backend_py.main:app --host 0.0.0.0 --port 8000
HOST=0.0.0.0 PORT=4177 node server.mjs
# ALLOWED_ORIGINS="http://<内网IP>:4177" 传给 uvicorn 进程
```
**反代同源(推荐,Caddy 例)**:
```
<内网IP或主机名> {
  handle /api/* { reverse_proxy 127.0.0.1:8000 }
  handle        { reverse_proxy 127.0.0.1:4177 }
}
```
**安全提醒**:内网默认信任,但 scanner 写端点仍裸露;若内网不完全可信,直接套档 3 的鉴权。

---

## 档 3 — 公网 / 对外(任何人能访问)
**适用**:挂到公网域名给外部访问。**在档 2 基础上,把"无鉴权 + 写端点"这个洞堵死,加 TLS。**

**必须做:**
1. **档 2 的 3 处改动**(API_BASE 相对化、绑定、CORS 环境变量)。
2. **反代 + HTTPS**(Caddy 自动签证书):
   ```
   your-domain.com {
     handle /api/* { reverse_proxy 127.0.0.1:8000 }
     handle        { reverse_proxy 127.0.0.1:4177 }
   }
   ```
   `ALLOWED_ORIGINS=https://your-domain.com`。
3. **鉴权(关键)** —— 三选一:
   - **(最稳)反代层 Basic Auth / OAuth**:在 Caddy/nginx 给整站或至少 `POST /api/scanner/*` 加认证。
   - **应用层 token**:给状态变更端点要求 `Authorization: Bearer <token>`(需在 `main.py` 加依赖校验 + 前端注入)。
   - **(最简)直接禁用公网写端点**:若公网只读看盘,在反代层 `POST /api/scanner/*` 一律 403,数据刷新只在服务器本地定时跑。**推荐这条**——展示站不需要让访客触发重算。
4. **绑定收回 localhost**:uvicorn 和 server.mjs 仍绑 `127.0.0.1`,**只让反代对外**,应用进程不直接暴露:
   ```bash
   uv run uvicorn backend_py.main:app --host 127.0.0.1 --port 8000   # 反代在前面
   PORT=4177 node server.mjs                                          # 仍绑 127.0.0.1
   ```
5. **进程守护**(systemd 例,两个 unit:api + static),崩溃自启。
6. **数据定时刷新**(cron / systemd timer,服务器本地、联网 OKX):
   ```cron
   # 每天 00:30 刷新报告(示例)
   30 0 * * *  cd /srv/whd && uv run python -m backend_py.run_data_pipeline --download-only --days 3650 && uv run python -m backend_py.run_full_pipeline --skip-download --official --days 3650 --bars "1D,4H,8H,1W"
   ```

**建议加固(非必须但推荐):**
- 反代加**限流**(scanner 即便加了 auth 也限并发)。
- 去掉响应里的绝对路径泄露(审计 L1:`_source.reportPath` / `/health` 的 `multiPeriodReportPath`)。
- 监控:`/health` 做存活探针。

---

## 4. 三档对比速查
| 维度 | 档1 本地 | 档2 内网 | 档3 公网 |
|---|---|---|---|
| 改代码 | 无 | API_BASE + 绑定 + CORS(3 处) | 档2 + 鉴权 + 反代TLS |
| 绑定 | 127.0.0.1 | 0.0.0.0 / 反代 | 仅反代对外,应用回收 127.0.0.1 |
| 鉴权 | 不需要 | 视内网信任 | **必须**(或禁用写端点) |
| HTTPS | 不需要 | 可选 | 必须 |
| 数据刷新 | 手动 | 手动/定时 | 定时(服务器本地) |
| scanner 写端点 | 本机可用 | 内网可用(慎) | **建议禁用或锁死** |

## 5. 定位提醒(写给运维/对外文案)
- 本系统是**市场状态/天气描述器 + 风控背景层**,**不产生买卖信号**(见 `gate1-conclusion.md`)。对外页面/说明**禁止**任何"预测涨跌/跟单"暗示。
- 概率旁已有样本/置信标注(L5),小样本弱化;公网展示尤其要保留,防误读成确定性。
