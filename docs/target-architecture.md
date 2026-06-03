# 目标架构(Target Architecture)

> 留痕文档。固化当前已落地的三层架构与"暂不引入 Rust"的决策,供后续维护者一眼看懂边界。
> 现状基线:Python official 全周期(1D/4H/8H/1W)对 Node `FAIL=0`,生产报告已由 Python 写出。

## 一句话
**Python 负责"算 + 数据",REST(FastAPI)是唯一对外窗口,前端只负责"摆盘展示"。** 三层单向依赖,各司其职。

## 分层职责
| 层 | 技术 | 职责 | 不该做的事 |
|---|---|---|---|
| **计算 + 数据层** | Python(`backend_py/`) | 下载/清洗行情、跑研究算法(feature factory / deviation rules / market weather router / router backtest+calibrator)、写 `reports/` official 产物、读写 `data/` | 不直接面向浏览器;不内嵌业务展示逻辑 |
| **接口层(窗口)** | FastAPI REST(`backend_py` API) | 把 `reports/` 与 `data/clean` 以 `/api/...` 暴露;`/api/dashboard/current`、`/api/candles`、`/api/market/symbols`、`/api/reports/*` | 不重算研究指标(只读已生成产物);不藏计算 |
| **展示层(摆盘)** | 静态前端(`app.js` / `index.html` / `styles.css`) | 取 REST 数据渲染;品种/周期选择;小样本弱化;API 挂了时回退读静态 `reports/` 文件 | 不算指标、不造数据;`current=null` 走"样本不足"占位、不崩 |

## 数据流(单向)
```
OKX → [Python 下载/清洗] → data/clean
                              │
            [Python 研究算法] → reports/*.json  (official)
                              │
                  [FastAPI REST]  ──/api/──▶  [前端 app.js] ──▶ 浏览器
                              │                        ▲
                              └── 静态文件回退 ─────────┘ (API down 时前端直读 reports/)
```

## 关键约束
- **REST 是唯一的门**:前端默认走 `/api/dashboard/current`;失败才回退直读静态 JSON(同一份 official 产物),保证离线/API 挂掉也能看。
- **前端不持有真理**:任何概率/状态都来自后端 official 产物;前端只做格式化 + 语境标注(样本/置信)。
- **Node 仅剩前端静态 server(`server.mjs`)与待删的研究脚本**:研究/生成的 Node 代码即将退役(见 `node-retirement-checklist.md`),前端文件保留。

## 为什么暂不引入 Rust(决策留痕)
- **没有热点瓶颈值得换语言**:当前算力瓶颈在 IO/数据量,不在 Python 数值内核;Python+NumPy 已够。
- **跨语言对平刚打完一场硬仗**:Python↔Node 的逐字对平(见 `parity-helpers.md`)耗费很大;再引入 Rust 等于再开一条"三方对平"战线,收益不抵成本。
- **团队/工具链单一更省心**:数据、研究、API 全 Python,一套依赖、一套测试。
- **结论**:**现在不引入 Rust**。若将来出现明确的、可量化的性能瓶颈(如实时逐 tick、超大截面扫描),再单独立项评估,届时优先考虑把**单个热点函数**用 Rust/Cython 包起来,而非重写全栈。

## 与其他文档的关系
- 砍 Node 的前置条件与顺序:`node-retirement-checklist.md`
- 跨语言对平的三个数值/字符串助手:`parity-helpers.md`
- 剩余 Node 命令清单:`remaining-node-command-inventory.md`
- 总方向:`roadmap.md`;分步执行:`next-steps.md`
