# 下一步执行计划(Codex 分步执行)

> 代码基线:`main @ c895b7d`(Python official parity cutover 已完成,1D/4H/8H 全量 `FAIL=0`)。
> 本文件把剩余工作排成有依赖顺序的 N 步,供逐步执行。配合 `roadmap.md`(总方向)与各专项 spec 使用。

## 全局铁律(每步都适用)
- **一次只做一个 N 步**,做完停下报告,确认后再下一步。
- 不改研究算法逻辑;parity-helper / 测试脚本 / 前端展示属允许范围。
- 任何对账没到 `FAIL=0` 或冒出预期外失败 → **停下贴明细**,不要改逻辑绕过。
- 每步一次干净提交;`reports/` 的任何临时覆盖必须 `git restore` 还原,**绝不提交 Node 临时覆盖**。
- 需要联网 / 写 `data/` 的步骤,**先问用户放行**。

---

## N1 — 把全量对账固化成"一键回归" 🔒 不联网【建议第一个做】
**目标**:把手工跑通的 4b 变成随时能复跑的回归脚本——以后任何改动都能一键验证 Python==Node。这是砍 Node 的前置条件②。
**范围**:
- 新增 `backend_py/run_parity_check.py`(或 `scripts/parity_check.sh`):自动跑「Node 重生成 → Python `_py` 影子 → 全 58 ×(1D/4H/8H)`compare_feature_factory/router/deviation` + `compare_summary` → 打印 `PASS/FAIL` → **`finally`/`trap` 里 `git restore reports` 还原 official + 清 `_py`**」。
- (推荐、更稳)给 `compare_*.py` 加 `--node-suffix/--python-suffix` 双路径参数,让回归**完全不碰正式名**(Node 写 `_node`、Python 写 `_py`、比这两个),从根上消除"临时覆盖正式名"的风险。
**不该动**:任何研究算法、`data/`。
**完成定义**:一条命令跑出 `PASS=522 FAIL=0`;脚本中断也能自动还原 official、工作区干净;`verification-log` 加一节。
**依赖**:无。**先做**(它保护后面所有改动)。
**提交**:`test(parity): one-button full parity regression`。

## N2 — 1W 收口 🌐 需联网 + 写 data/(先问放行)
**目标**:补齐周线,四周期口径统一。
**范围**:下载 1W(58 品种)raw+clean → Python official 生成 1W → 跑 N1 回归(扩到含 1W)到 `FAIL=0` → 1W 纳入 default bars + combined summary → 删/归档**陈旧的 Node 1W 报告**。
**不该动**:1D/4H/8H 已对平产物。
**完成定义**:1W 也 `FAIL=0`;`reports/` 不再混旧 Node 1W;combined 含 1W。
**依赖**:N1(用同一把尺子验 1W)。

## N3 — 前端 M3:品种/周期选择器 🖥️ 不联网
**目标**:网页不再硬编码 BTC/1D,能切币切周期。
**范围**:严格按 `docs/frontend-m3-spec.md`:URL 参数 `?instrument=&bar=` + `buildPaths()`(**主路和 fallback 都按所选重建**)+ 选择器(从 `/api/market/symbols` 填充)。**只动 `app.js` / `index.html` / 可能 `styles.css`,后端不动。** 保 M4/M5 不破。
**完成定义**:`?instrument=ETH-USDT&bar=4H` 正常;切换更新 URL+重渲染;薄历史走 M5 占位不崩;API 关掉时 fallback 用**所选品种**文件(非 BTC);`node --check app.js` 过。
**依赖**:M5(已完成)。

## N4 — 前端 L5:概率带样本/置信 🖥️ 不联网
**目标**:概率旁标样本数/置信,别误读成确定性。
**范围**:`app.js` 英雄卡 + 结论文案,复用后端已给的 `occurrences/confidence`;小样本弱化展示。只动前端。
**完成定义**:概率处显示样本/置信;小样本态有明显弱化样式。
**依赖**:N3。

## N5 — 填 `verification-log` 剩余 TODO 🌐 部分需联网
**目标**:把仍是 `TODO` 的几节(H4 下载真实 rowCount、7b/7c 降级证据等)用真实数字补上,验证闭环。
**范围**:只填 `verification-log.md`;需联网的随 N2 一并采集。
**完成定义**:无遗留 `TODO`(或注明"环境受限暂缺")。
**依赖**:N2(同一次联网采数)。

## N6 — 文档留痕(收尾)📄 不联网
**目标**:固化架构与退役标准。
**范围**:新增 `docs/target-architecture.md`(Python 算+数据 / REST 当窗口 / 前端摆盘;Rust 暂不引入决策)、`docs/node-retirement-checklist.md`(砍 Node 前置 + 顺序)、`docs/parity-helpers.md`(jsround/jssum/jsnumber 留痕)。纯文档。
**依赖**:无,随时可做。

## N7 — 冻结 golden 接管"标准答案",然后砍 Node 🔒 不联网【删 Node 的真正前提】
**背景**:Node 从来不是线上服务,只是本地生成报告的脚本——**所以没有"运行时观察期"这回事**。但当前 N1 回归是**现场跑 Node 生成 golden 再比**,即 Node 仍兼着"标准答案"角色;**直接删 Node 会让 N1 回归失去比对基准**。删之前必须先把这个角色换走。
**步骤**:
1. **冻结 golden 快照**:钉一小批固定输入(pin 一份 `data/clean` 子集,纳入仓库或 `tests/fixtures/`)+ 对应"正确输出"快照存进 `tests/golden/`(这份输出 = 当前已对平的 Python official,等价 Node)。
2. **改造 N1**:从"现场跑 Node 生成 golden"改成 **Python 现算 vs 冻结 golden** 比对。改完 Node 不再是回归依赖。
3. **确认无入口再调 Node**:`package.json` 脚本、`scanner_service`、文档命令、`remaining-node-command-inventory` 全部清完/确认弃用。
4. **删 Node**:删 `backtest/*.mjs` 与 `scripts/*.mjs` 的研究/生成代码(`app.js`、`server.mjs`、`index.html` 等前端文件**保留**)。
5. 删完跑一遍改造后的 N1 + `smoke_test`,确认安全网仍在。
**不该动**:`app.js`/`server.mjs`/前端;Python 研究算法。
**完成定义**:Node 研究代码已删;改造后的 N1(Python vs 冻结 golden)`FAIL=0`;无任何脚本/入口再调 Node。
**依赖**:① N2(1W 也对平,趁 Node 还在做完);② ④ 入口清完。**这之后即可删,无需等待期。**

---

## 砍 Node 前置条件(到齐才动手删 —— 无"观察期")
| 条件 | 当前 |
|---|---|
| ① Python↔Node 全量逐字对平 | ✅ 1D/4H/8H(1W 待 N2) |
| ② 对账沉淀成可复跑回归 | ✅ N1(`04bedc0`) |
| ③ **冻结 golden 接管"标准答案"**(N1 不再依赖现场 Node) | ⬜ N7 |
| ④ Node 入口全迁/弃用 | 🟡 `remaining-node-command-inventory` 在清 |
| ⑤ 前端全走 REST、不靠 Node | 🟡 N3 进行中 |

> 注:原"Python 生产观察一段"已删除——Node 非线上服务,无运行时可观察;真正的门槛是 ③(用冻结快照接管回归基准)。

**顺序建议**:N1✅ → N3+N4(前端,不联网)→ 放行联网时 N2+N5 → N7(冻结 golden + 删 Node)→ N6 收尾。**满足 ①–⑤ 即删,不设等待期。**

---

## 更远(不在本计划展开,单列)
- **闸门1 — alpha 验收回测**:TREND/RANGE 命中率、跨年、切换滞后、参数冻结。"能不能辅助交易"的关,属另一个大阶段。
- **二次加工层**:横截面扫描 / 多周期共振 / 事后记分卡。等上面稳了再启。
