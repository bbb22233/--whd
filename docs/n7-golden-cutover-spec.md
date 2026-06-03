# N7 施工方案:冻结 golden 接管标准答案 → 删 Node(在本机/有数据环境执行)

> 只读施工方案。**在有 `data/clean` 的环境(用户本机 Mac,或网络放行 OKX 后先下载)执行**;Web 一次性容器无源数据、OKX 403,做不了(见 `node-retirement-checklist.md` 的环境约束节)。
> 延续既有模式:本文件出 spec,本机 codex 逐步执行,每步过验证闸后再下一步。**铁律:跑通"Python vs 冻结 golden `FAIL=0`"之前不删 Node。**
> 配套:`next-steps.md`(N7)、`node-retirement-checklist.md`、`parity-helpers.md`。代码基线:`main`(N6 已并入)。

---

## 0. 思路一句话
当前 N1(`run_parity_check.py`)是**现场跑 Node 生成 golden 再比**——Node 仍兼"标准答案"。本步把标准答案换成**仓库里冻结的小快照**(`tests/fixtures` 输入 + `tests/golden` 输出),让 N1 改成 **Python 现算 vs 冻结 golden**,从此不依赖 Node,然后才删 Node 研究代码。

## 1. Fixture 选样(小而有代表性 —— 专门守住 4 个 parity 助手 + 不足态)
| 品种 | 守住什么 |
|---|---|
| **BTC-USDT** | 深历史、正常态(样本通过);基准 |
| **SOL-USDT** | `js_round` 真实事故(SOL 8H medianPositionPct 50.48/50.49) |
| **DOGE-USDT** | `js_sum` 真实事故(DOGE 4H featureStats 朴素累加) |
| **ENA-USDT** | 薄历史 → `current=null`/不足态 → 守 `None` 键省略的序列化修复 |

- 周期:`1D,4H,8H`(若 N2 已联网对平 1W,加 `1W`)。
- `--days`:**沿用生产口径 3650**(保证 fixture 输出 = 当前 official,避免另立口径)。4 品种 × 3 周期 = 12 格,体量可控。

## 2. Step A — 新增冻结脚本 `backend_py/freeze_golden.py`(运行一次,产出 fixture)
**作用**:从真 `data/clean` 取这 4 品种的 clean 输入 → 跑 Python official 三件套 + 两份 summary → 把**输入**拷进 `tests/fixtures/data/clean/`、**输出**拷进 `tests/golden/`。两者一起提交,即"冻结的标准答案"(= 当前已对平 Node 的 Python official)。

建议实现(codex 可微调,复用 `run_parity_check.py` 既有函数):
```python
# backend_py/freeze_golden.py
from __future__ import annotations
import shutil, sys
from pathlib import Path
from backend_py.reports_reader import DATA_CLEAN_DIR, PROJECT_ROOT, REPORTS_DIR
from backend_py.research.config import parse_args as parse_research_args, file_stem, report_stem
from backend_py.build_feature_factory import main as build_feature_factory
from backend_py.build_deviation_rules import main as build_deviation_rules
from backend_py.build_market_weather_router import main as build_market_weather_router

FIXTURE_SYMBOLS = ["BTC-USDT", "SOL-USDT", "DOGE-USDT", "ENA-USDT"]
FIXTURE_BARS = ["1D", "4H", "8H"]          # N2 后可加 "1W"
DAYS = 3650
KINDS = ("feature_factory", "deviation_rules", "market_weather_router")
FIXT_DIR = PROJECT_ROOT / "tests" / "fixtures" / "data" / "clean"
GOLD_DIR = PROJECT_ROOT / "tests" / "golden"

def main() -> None:
    FIXT_DIR.mkdir(parents=True, exist_ok=True)
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    for bar in FIXTURE_BARS:
        for symbol in FIXTURE_SYMBOLS:
            cfg = parse_research_args(["--instrument", symbol, "--bar", bar, "--days", str(DAYS)])
            stem, name = file_stem(cfg), report_stem(cfg)
            src_clean = DATA_CLEAN_DIR / f"{stem}_clean.json"
            if not src_clean.exists():
                sys.exit(f"missing input {src_clean}; ensure data/clean has the fixture symbols")
            shutil.copyfile(src_clean, FIXT_DIR / f"{stem}_clean.json")     # pin INPUT
            args = ["--instrument", symbol, "--bar", bar, "--days", str(DAYS)]
            build_feature_factory(args); build_deviation_rules(args); build_market_weather_router(args)
            for kind in KINDS:                                             # pin OUTPUT
                shutil.copyfile(REPORTS_DIR / f"{name}_{kind}.json", GOLD_DIR / f"{name}_{kind}.json")
    print(f"frozen {len(FIXTURE_SYMBOLS)*len(FIXTURE_BARS)} cells into tests/fixtures + tests/golden")

if __name__ == "__main__":
    main()
```
> 注:summary 的两份(`multi_<bar>_market_weather_current` / `multi_period_...`)在 golden 模式里由 Python 现场从 `_py` 重建并比对(见 Step B 的 `build_summary_from_suffix`),不必单独冻结整文件——只需冻结上面三件套即可,summary 的逐字段对平由 `compare_summary` 在 fixture 子集上保证。若想更严,也可把这两份 summary 一并冻结(codex 定)。

**验证闸 A**:`tests/fixtures/data/clean/` 有 12 个 `_clean.json`,`tests/golden/` 有 36 个 `_*.json`;git 里这两目录**不被 ignore**(见 Step E 的 `.gitignore` 调整)。

## 3. Step B — 改造 `run_parity_check.py`:加 `--golden` 模式 + 修死路径
**两处改动:**

### B-1 修掉写死的 Mac 路径(`parity_env`)
当前 `parity_env()` 写死 `/Users/guanlan/...`,换机即废。改成通用发现:
```python
import shutil
def parity_env() -> dict[str, str]:
    env = os.environ.copy()
    node = shutil.which("node")
    if node:
        env["PATH"] = f"{Path(node).parent}:{env.get('PATH','')}"
    return env
```

### B-2 加 `--golden` 模式(不跑 Node)
- 新增 `--golden`(布尔)。开启时:
  1. **不**调 `run_node_golden`;改为 `stage_golden_as_node()`:把 `tests/golden/<name>_<kind>.json` 拷成 `reports/<name>_<kind>_node.json`(占用既有 `_node` 基线位,下游 compare 完全复用、零改动)。
  2. **Python 现算走 fixture 数据**:`build_python_shadows` 里三件套 builder 改为**子进程**调用,并注入 `RESEARCH_DATA_CLEAN_DIR=tests/fixtures/data/clean`(配合 B-3 的单点覆盖),保证读的是冻结输入而非本机真 `data/clean`。
  3. 其余(compare_*、build_summary_from_suffix、compare_summary、`finally` 清理)**原样复用**。
  4. golden 模式默认 `--symbols=FIXTURE_SYMBOLS --bars=1D,4H,8H`。
- `stage_golden_as_node` 收尾要把它拷进 reports 的 `_node` 文件清掉(已有 `remove_suffix_artifacts(_node,_py)` 覆盖)。

### B-3 让 `DATA_CLEAN_DIR` 认环境变量(reports_reader.py 单行)
```python
import os
DATA_CLEAN_DIR = Path(os.environ.get("RESEARCH_DATA_CLEAN_DIR") or (PROJECT_ROOT / "data" / "clean"))
```
> 因 `run_parity_check` 在进程内直接调 builder,B-2 选**子进程**调用 builder 才能让该环境变量生效(进程内 import 已固化 DATA_CLEAN_DIR);或者把三件套 builder 的 `DATA_CLEAN_DIR` 读取改成函数内动态读 `os.environ`。两法二选一,codex 选低风险者并验证。

**验证闸 B(关键!)**:
```
uv run python -m backend_py.run_parity_check --golden
```
必须打印 `PASS=36 FAIL=0`、`SUMMARY=ok`、工作区 `reports/` 干净(`finally` 已还原)。**此闸不过 → 停,贴明细,绝不删 Node。**

## 4. Step C — 双轨并存自检(删前最后一道保险)
在删 Node 前,确认两条 N1 都绿:
- 老路(现场 Node,仅在有 Node 的本机):`uv run python -m backend_py.run_parity_check`(全 58 品种)→ `FAIL=0`。
- 新路(冻结 golden,任何环境):`... --golden` → `FAIL=0`。
两者都绿 = 冻结 golden 确实等价 Node,可以放心切换。

## 5. Step D — 清入口(`package.json` + 清单)
- 删 `package.json` 里所有 `legacy:*`(它们指向待删的 `scripts/*.mjs`)与 `backtest:indicators/volatility/position/deviations`、`train:*`、`validate:trees`、`compare:macro`、`journal:create`(确认无人依赖后)。
- **保留** `serve`(`node server.mjs`,前端静态)。
- 更新 `docs/remaining-node-command-inventory.md`:把已删项标"removed",保留项(`serve`)说明。
- `grep -rn "\.mjs" package.json scripts/ backend_py/ docs/` 确认无残留指向待删文件的入口(`run_parity_check` 的 `run_node_golden` 在 golden 模式下已不走;可保留老路函数仅供本机全量回归,或一并删——见 Step E 决策)。

## 6. Step E — 删 Node 研究代码 + `.gitignore` 调整
**删(研究/生成):**
- `backtest/*.mjs` 全部(算法实现:clean/config/deviation-*/feature-factory/market-weather-router/io/okx/strategy-*/indicators/market-state/volatility-state/position-state/router-calibrator/som/state-features/decision-*)。
- `scripts/*.mjs` 全部(`run-multi-symbol-1d`/`build-*`/`backtest-*`/`calibrate-router`/`download-*`/`clean-data`/`train-*`/`validate-*`/`compare-macro-impact`/`create-decision-journal`)。

**保留(前端):** `app.js`、`server.mjs`、`index.html`、`styles.css`。

**`run_parity_check.py` 收尾:** 删 `run_node_golden`/`copy_node_golden`/`parity_env`/`run_subprocess` 等只为 Node 服务的函数(若 Step C 想留老路全量回归,则保留这些并保留 Node——但那等于没删干净;**推荐**:既然 golden 已接管,直接删 Node + 删这些函数,N1 只留 golden 模式)。

**`.gitignore`:** 确保 `tests/fixtures/` 与 `tests/golden/` **不被忽略**(它们是回归资产);`data/` 仍忽略。

## 7. Step F — 删后总验
1. `uv run python -m backend_py.run_parity_check --golden` → `PASS=36 FAIL=0`、`SUMMARY=ok`。
2. `uv run python -m backend_py.smoke_test`(若存在)→ 绿。
3. `node --check app.js` → 过(前端 Node 仍在)。
4. `grep -rn "backtest/.*\.mjs\|scripts/.*\.mjs" .` 仅余前端无关项 / 文档历史引用。
5. FastAPI 起服 + 前端冒烟一遍,确认产线不依赖被删代码。

## 8. 完成定义
- 改造后 N1(Python vs 冻结 golden)`FAIL=0`,**不再 import/spawn 任何研究 `.mjs`**。
- Node 研究代码已删;前端 `app.js`/`server.mjs` 保留可用。
- `tests/fixtures` + `tests/golden` 已提交;`remaining-node-command-inventory` 收口。
- 砍 Node 前置表 ①–⑤ 全 ✅。

## 9. 提交粒度建议
1. `test(parity): freeze golden fixture + golden mode (no Node)` —— Step A+B+C(含 fixtures/golden 资产)。
2. `chore(node): remove legacy node research entrypoints` —— Step D。
3. `chore(node): delete node research code; parity runs on frozen golden` —— Step E+F。
> 删除是 git 操作可 revert;但务必 1→2→3 顺序,且每步过验证闸。
