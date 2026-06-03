# 砍 Node 检查清单(Node Retirement Checklist)

> 留痕文档。固化"删 Node 研究/生成代码"的前置条件与执行顺序。
> 核心认知:**Node 从来不是线上服务**,只是本地生成报告的脚本——**所以没有"运行时观察期"**。真正的门槛是把"标准答案"角色从现场 Node 换成冻结快照(N7-③)。
> 配套:`next-steps.md`(N7)、`target-architecture.md`、`parity-helpers.md`、`remaining-node-command-inventory.md`。

## 保留 vs 删除(边界先说清)
- **保留**:`app.js` / `server.mjs` / `index.html` / `styles.css` —— 前端与静态 server,不在退役范围。
- **删除目标**:研究/生成的 Node 代码,即 `backtest/*.mjs`(算法实现)与 `scripts/*.mjs`(研究/生成入口)中已被 Python official 取代的部分。
- **`package.json`**:清掉 `legacy:*` 与已迁移命令对应的 Node 脚本项;保留 `serve`(静态)。

## 前置条件(到齐才动手删 —— 无观察期)
| # | 条件 | 当前状态 |
|---|---|---|
| ① | Python↔Node 全量逐字对平 `FAIL=0` | ✅ 1D/4H/8H(/1W 视 N2 联网补齐) |
| ② | 对账沉淀成可复跑回归 | ✅ N1 `run_parity_check.py`(`04bedc0`) |
| ③ | **冻结 golden 接管"标准答案"**(N1 不再依赖现场 Node) | ✅ N7 frozen fixture/golden |
| ④ | Node 入口全迁/弃用 | ✅ legacy entrypoints removed; only `serve` remains |
| ⑤ | 前端全走 REST、不靠 Node | ✅ N3(API-down fallback 用所选品种静态文件) |

> ③ 是真正的拦路虎:当前 N1 是**现场跑 Node 生成 golden 再比**,即 Node 仍兼着"标准答案"。直接删 Node 会让 N1 失去比对基准。

## 执行顺序(= N7)
1. **冻结 golden 快照**:pin 一小批固定输入(`data/clean` 子集,纳入 `tests/fixtures/`)+ 对应"正确输出"快照存 `tests/golden/`(这份输出 = 当前已对平的 Python official,等价 Node)。
2. **改造 N1**:从"现场跑 Node 生成 golden"改成 **Python 现算 vs 冻结 golden** 比对。改完 Node 不再是回归依赖。
3. **确认无入口再调 Node**:`package.json` 脚本、`scanner_service`、文档命令、`remaining-node-command-inventory` 全部清完/确认弃用。
4. **删 Node 研究代码**:删 `backtest/*.mjs` 与 `scripts/*.mjs`(前端 `app.js`/`server.mjs`/`index.html` 保留)。
5. **回归兜底**:删完跑改造后的 N1 + `smoke_test`,确认安全网仍在。

## 删除前自检清单
- [x] N1 已改为"Python vs 冻结 golden",且 `FAIL=0`(不再 import/调用任何 `.mjs`)
- [x] `grep -rn "\.mjs" package.json scripts/ backend_py/ docs/` 无残留指向待删文件的入口;剩余为历史规格/日志引用
- [x] `scanner_service` / 任何 API 不再 spawn Node 研究脚本
- [x] `remaining-node-command-inventory.md` 里待删项已确认无人依赖(legacy 回退已不需要)
- [x] 前端冒烟:`node --check app.js`,页面正常渲染(前端 Node 仍保留)

## 完成定义
- Node **研究代码已删**;改造后的 N1(Python vs 冻结 golden)`FAIL=0`;无任何脚本/入口再调被删的 Node。
- 前端(`app.js`/`server.mjs`)不受影响。

## ⚠️ 环境约束:N7 不能在 Web/一次性容器里做(2026-06 实测)
冻结 golden 的本质是**把输入 `data/clean` 子集 pin 进仓库**,再让 Python 重算去比。但在 Claude Code Web 的一次性容器里实测发现:
- `data/` 被 `.gitignore`,**源数据不随仓库走**,容器重建后 `data/clean` 为空;生成已提交 `reports/` 的那批快照已随旧容器回收。
- 网络策略**封禁 OKX**(下载实测 `HTTP 403 Forbidden`),无法现取数据补。
- 仓库里**没有任何 candle/clean/fixture** 可作输入(reports 只存派生特征,不含原始 OHLCV)。
→ 没有输入数据,既跑不了现有 N1,也无法冻结"输入+输出"fixture,更无法验证改造后的回归。
**因此 N7 必须在有 `data/clean` 的环境执行**(用户本机 Mac,或网络策略放行 OKX 后先下载一小批固定子集)。
**铁律**:在能跑通"改造后 N1(Python vs 冻结 golden)`FAIL=0`"之前,**不得删 Node**——否则回归安全网会断且无法当场验证。

## 风险与回滚
- 删除是 git 操作,**可 revert**;但删前务必先完成步骤 1–2(冻结 golden),否则回归网会断。
- 若 1W 尚未联网对平(N2 未做),可先删 1D/4H/8H 相关无歧义部分,1W 相关保留到 N2 完成——**但更稳的做法是 N2 先行**,一次性删干净。
