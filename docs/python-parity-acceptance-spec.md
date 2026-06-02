# Python Official Cutover — 全量 Parity 验收规格

> 只读施工/验收方案,执行由本地完成(需联网/本地 `data/clean`)。
> 背景:`675b532` 已把 Python 设为正式 report writer,但**全品种 Node↔Python 一致性对账从未做过**(只 BTC/ETH × 1D/4H,见 verification-log §10–13)。本规格给出"安全做一次全量对账"的流程,作为 cutover 的**真正验收闸**。
> 代码基线:`main @ c3798ca`。

---

## 0. 为什么需要这道闸
- cutover 的"验证"只是 **174 个跑通、0 报错**(§35),**不等于 Python 输出 == Node 输出**。
- 其余 ~56 个品种 × 各周期没有任何一致性记录,而 Python 已占用正式 `reports/`。
- 这是流程缺口,不是已知代码错误(代码 parity 上轮已逐行核对、忠实)。低概率踩雷,但某个冷门品种口径若有差,现在难发现。

## ⚠️ 1. 必读陷阱:对账脚本的"槽位"假设已失效
`backend_py/compare_*.py` 写死两个路径:
```python
# compare_market_weather_router.py:74-75
node_path   = REPORTS_DIR / f"{stem}_market_weather_router.json"      # 假定=Node golden
python_path = REPORTS_DIR / f"{stem}_market_weather_router_py.json"   # =Python 影子
```
**cutover 后正式名(`{stem}_..._router.json`)已经是 Python 产物**。此刻直接跑 `compare_*` = **Python vs Python 自比,必然全 ok,毫无意义**。
→ 必须**先把 Node 重新写回正式名(临时覆盖)**,再生成 Python `_py` 影子,才能做真对账;比完**还原 Python official**。

## 2. 安全前提
- `git status` 干净(当前 `reports/` = Python official,已提交)。
- 本地 `data/clean` 覆盖 174/174(cutover 前提已满足)。
- 全程**不并发**跑别的 report writer。
- 结束必须还原 official(见 §6),不要把临时 Node 覆盖提交上去。

## 3. 流程

### Step A — 用 Node 重生成正式名(临时覆盖,全 174 × 1D/4H/8H)
```bash
node scripts/run-multi-symbol-1d.mjs --skip-download --bars 1D,4H,8H
```
- 这会用**修复后的 Node 代码**(当前 `backtest/*.mjs`)把 `{stem}_feature_factory.json / _market_weather_router.json / _deviation_rules.json / multi_*` 写回正式名,**临时覆盖 Python official**。
- `--skip-download` 复用本地 `data/clean`,不联网。
- 期望:`successCount≈174, errorCount=0`(与 Python official 的覆盖面一致)。

### Step B — 生成 Python `_py` 影子(全 174 × 1D/4H/8H)
对每个 symbol×bar 跑三个 build(写 `_py` 后缀),例如循环:
```bash
SYMBOLS="$(python3 -c 'from backend_py.build_summary import DEFAULT_SYMBOLS; print(" ".join(DEFAULT_SYMBOLS))')"
for s in $SYMBOLS; do for b in 1D 4H 8H; do
  uv run python -m backend_py.build_feature_factory      --instrument "$s" --bar "$b" --days 3650
  uv run python -m backend_py.build_market_weather_router --instrument "$s" --bar "$b" --days 3650
  uv run python -m backend_py.build_deviation_rules       --instrument "$s" --bar "$b" --days 3650
done; done
```
> 若已有 scanner 批量模式(`python_research` 等)能一次写全 `_py`,优先用它,等价即可。

### Step C — 全量对账(Node 正式名 vs Python `_py`)
```bash
PASS=0; FAIL=0; FAILS=""
for s in $SYMBOLS; do for b in 1D 4H 8H; do
  for cmp in compare_feature_factory compare_market_weather_router compare_deviation_rules; do
    if uv run python -m "backend_py.$cmp" --instrument "$s" --bar "$b" --days 3650 >/dev/null 2>&1; then
      PASS=$((PASS+1)); else FAIL=$((FAIL+1)); FAILS="$FAILS\n$cmp $s $b"; fi
  done
done; done
echo "PASS=$PASS FAIL=$FAIL"; echo -e "$FAILS"
```
期望:`FAIL=0`。任何 fail → 单独重跑该 `compare_*`(不加 `2>/dev/null`)看 `failures` 明细。

### Step D — Summary parity
```bash
uv run python -m backend_py.compare_summary --from-reports --symbols $SYMBOLS --bars 1D,4H,8H
```

### Step E(可选)— 抽样人工眼检
即便全 ok,挑 **薄历史 / meme / 各周期** 各几个(WLD/ORDI/SUI/PEPE × 4H/8H),`jq` 比 `current.gate`、`strategyScores`、`currentCalibrationSignals` 是否一致。harness 已很紧,这步只是兜底。

## 4. 判定标准
- **通过**:Step C `FAIL=0` 且 Step D `status ok`。
- **不通过**:任何 `failureCount>0`。需定位是
  - 真数值差异(>1e-3)→ 移植 bug,必须修;
  - 还是 `OPTIONAL_KEYS`(`confidenceLimited / metricBucketMode`)这类"旧 golden 缺字段"——但本流程的 golden 是**当前修复后 Node 现生成的**,不应缺这些字段,所以**这里不该靠豁免通过**,出现即视为真差异。

## 5. 还原 official(务必执行)
对账完,正式名现在是 Node 的临时覆盖,必须还原成 Python official:
```bash
git restore reports            # 还原到 cutover 后的 Python official
# 或重新生成:
# uv run python -m backend_py.run_full_pipeline --skip-download --official --bars 1D,4H,8H --days 3650
git status --short             # 确认 reports 无残留改动;清掉临时 _py 影子(若不想留)
```

## 6. 1W 收口(单独决策)
cutover 只做了 1D/4H/8H,`reports/` 里**还混着旧 Node 的 1W**,且 combined summary 已丢 1W。二选一:
- (a) 用 Python official 把 1W 也重生成,纳入 default bars 与 combined;或
- (b) 明确从 default bars 移除 1W,并删/归档旧 1W 文件。
**不要让 production 长期混着 Python 1D/4H/8H + 陈旧 Node 1W。**

## 7. 影响范围
- **不改任何源代码**(纯运行 + 对账 + 还原)。
- 临时覆盖只在 `reports/`,靠 `git restore` 还原,零持久影响。
- **不该动**:`backtest/*`、`backend_py/*` 算法;`data/`。

## 8. 可选小增强(需你点头才动代码)
当前"临时覆盖正式名 + 还原"略危险(中途中断会留下 Node 覆盖)。更稳的做法:给 `compare_*` 加**显式双路径参数**(`--node-path/--python-path` 或 `--node-suffix _node`),这样 Node golden 写到 `_node` 后缀、Python 写 `_py`,正式名(Python official)**全程不动**,对账更安全、可批量。这是小改动,但属代码改动,**先方案后改**。

## 9. 验收登记
通过后补成 `verification-log.md` 一节:贴 `PASS/FAIL` 计数、Step D 结果、抽样眼检截图/片段、以及 1W 收口决定。**这才是 cutover 的真正"通过"记录**(现 §35 只是"跑通了")。
