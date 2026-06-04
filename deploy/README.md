# 部署配置模板(deploy/)

> 配合 `docs/deployment-spec.md` 使用。这里是档③公网部署的**可直接套用模板**:反代 + 进程守护 + 定时刷数据 + 禁公网写端点。
> 所有占位(`your-domain.com` / `/srv/whd` / `User=whd` / uv·node 路径)按你的环境替换。

## 文件清单
| 文件 | 作用 | 目标位置 |
|---|---|---|
| `Caddyfile` | 反代 + 自动 TLS + 同源 + 403 掉 scanner 写端点 | `/etc/caddy/Caddyfile` |
| `whd-api.service` | FastAPI(uvicorn)守护,仅绑 127.0.0.1 | `/etc/systemd/system/` |
| `whd-static.service` | 前端静态(server.mjs)守护,仅绑 127.0.0.1 | `/etc/systemd/system/` |
| `whd-refresh.service` | 数据刷新(下载+生成报告),oneshot | `/etc/systemd/system/` |
| `whd-refresh.timer` | 每天 00:30 触发刷新 | `/etc/systemd/system/` |

## 一次性部署步骤
```bash
# 0) 准备代码 + 依赖(部署机)
git clone <repo> /srv/whd && cd /srv/whd
uv sync                      # 装 Python 依赖
# (首次)生成数据 + 报告 —— 需联网 OKX
uv run python -m backend_py.run_data_pipeline --download-only --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --official --days 3650 --bars "1D,4H,8H,1W"

# 1) 前端走同源:取消 index.html 里这行注释
#    <script>window.__API_BASE__ = "";</script>

# 2) 装 systemd unit + 启动
sudo cp deploy/whd-*.service deploy/whd-refresh.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now whd-api.service whd-static.service whd-refresh.timer

# 3) 反代
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
#    改 your-domain.com,DNS 指向本机
sudo systemctl reload caddy
```

## 验证
```bash
systemctl status whd-api whd-static          # 两个都 active (running)
curl -fsS https://your-domain.com/health     # {"status":"ok",...}
curl -i  -X POST https://your-domain.com/api/scanner/run   # 期望 403(公网写端点已禁)
# 浏览器开 https://your-domain.com/?instrument=BTC-USDT&bar=1D
```

## cron 替代(不用 systemd timer 时)
```cron
30 0 * * *  cd /srv/whd && uv run python -m backend_py.run_data_pipeline --download-only --days 3650 && uv run python -m backend_py.run_full_pipeline --skip-download --official --days 3650 --bars "1D,4H,8H,1W"
```

## 安全 / 定位提醒
- **公网只读**:`Caddyfile` 已 403 掉 `POST /api/scanner/*`,访客无法触发下载/重算/写盘。
- 应用仅绑 `127.0.0.1`,只有 Caddy 对外 → 应用本体不暴露。
- 可选加固:反代加限流;去掉响应里的绝对路径泄露(审计 L1)。
- **文案红线**:对外页面禁止任何"预测涨跌/跟单"暗示;雷达是**环境/风控描述器**,不是信号源(见 `gate1-conclusion.md`)。
