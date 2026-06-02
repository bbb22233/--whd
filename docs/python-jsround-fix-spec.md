# 修复规格:`js_round` 边界舍入差(Python parity 闸的拦路项)

> 只读施工方案,执行由本地完成。**这是 Python official cutover 全量对账(`python-parity-acceptance-spec.md`)唯一拦路的 bug。**
> 代码基线:`main @ 2ecdd41`。

## 1. 问题(已实锤)
全量对账在 `SOL-USDT 8H` 崩在一个字段:
```
ruleLibraryRows[5].medianPositionPct: node=50.48  python=50.49   (同组键/同样本数/同 median 原值 m=50.485)
```
根因:`backend_py/research/feature_factory.py:29` 的 `js_round` **不是** JS `Number.prototype.toFixed` 的忠实复刻:
```python
number = float(value) * factor            # 50.485*100 在浮点里被推成 5048.5
return math.floor(number + 0.5) / factor  # floor(5049.0)=5049 → 50.49
```
Node 用 `Number(m.toFixed(2))`,按真实 double(`50.48499…`)取整 → `50.48`。诊断已确认:
```
js_round(50.485,2)              = 50.49   (错,= 当前 Python)
Decimal(float(50.485)).quantize(0.01, HALF_UP) = 50.48   (对,= Node)
```
**性质**:跨语言取整在 `.xx5` 边界的差,装饰性(0.01),但 `js_round` 是**共享 helper**(被 `feature_factory / deviation_rules / market_weather_router / macro_data` 依赖),所以其它字段也可能零星 ±0.01,只是没都踩到边界。

## 2. 修复方案
把 `js_round` 改成按真实 double 取整、不做 `*factor` 预乘:
```python
from decimal import Decimal, ROUND_HALF_UP

def js_round(value, digits: int = 4) -> float:
    if not finite(value):
        return 0
    quant = Decimal(1).scaleb(-digits)                       # 10^-digits
    return float(Decimal(float(value)).quantize(quant, rounding=ROUND_HALF_UP))
```
- `Decimal(float(value))` 取的是 **double 的精确值**(`50.48499…`),`quantize(HALF_UP)` 与 Node `toFixed` 在所有**非精确半值**上一致(覆盖本数据几乎全部情况)。
- 只改 `feature_factory.py` 里的 `js_round` 定义一处;其余模块 import 它,自动生效。

### 备选(更快,但略不如上者忠实)
Python 内建 `round(float(value), digits)` 也按真实 double 取整(本例同样得 50.48),且**快得多**;差别仅在**精确半值 double**上是 banker's(就近偶数)而非 toFixed 的 half-up——这种值在本数据极罕见。若担心 Decimal 性能,可用内建 `round`,但需在备注里写明该取舍。**默认推荐 Decimal-HALF_UP(最忠实)。**

## 3. 影响范围
- **改**:`backend_py/research/feature_factory.py`(仅 `js_round` 函数体)。
- **不该动**:Node 侧(`toFixed` 是参考基准,正确,不动);任何算法逻辑;`data/`。
- **连带必须重做**(因为是共享 helper,输出会变):
  1. **重生成全部 Python official**(含 1W,见 §5):`run_full_pipeline --official`。
  2. **重跑全量 parity**(`python-parity-acceptance-spec.md`)到 `FAIL=0`。

## 4. 风险
- 该改动只会让 Python **更贴近 Node**(Node 是参考),不会引入新方向的偏差;理论上只减少 mismatch。
- 性能:Decimal 比 float 慢,`js_round` 调用极频繁。若全量管线明显变慢,改用备选内建 `round` 或加快路径;**先正确、再谈快**。
- 忠实度边角:负数精确半值上 `HALF_UP`(远离零)与 toFixed(取较大 n)方向可能不同——本数据几乎不触发,记为已知边角。

## 5. 顺带:1W 收口(同一次 official 重生成里做)
既然要重生成全部 official,**把 1W 一起补上**(你已倾向 Python 补齐 1W):
- official 重生成 bars 用 `1D,4H,8H,1W`。
- 全量 parity 也扩到含 1W(Node 侧同样要为 1W 现生成 golden 再比)。
- 收尾后 `reports/` 不再混着陈旧 Node 1W。

## 6. 验证(本地)
1. 单点先证:`SOL-USDT 8H` 重生成后 `ruleLibraryRows[5].medianPositionPct == 50.48`(= Node)。
2. 全量 parity(`python-parity-acceptance-spec.md` §3,bars 扩到 `1D,4H,8H,1W`)→ **`FAIL=0`** 且 summary `status ok`。
3. `node --check`/`py_compile`/`smoke_test` 仍过。
4. 还原/落定 official:用修好的 Python `--official` 写正式名(不要把 Node 临时覆盖留下)。
5. 把结果写进 `verification-log.md`:贴"修复前 50.49→修复后 50.48"、全量 `PASS/FAIL`、1W 纳入情况。

## 7. 提交粒度
- `fix(parity): faithful js_round via Decimal HALF_UP`(只含 `feature_factory.py` 改动)。
- 重生成的 official reports 单独一个提交 `chore: regenerate python official reports (jsround + 1W)`。
- `verification-log.md` 更新可并入或单独。

## 8. 完成定义(DoD)
- `js_round` 改完、`py_compile` 过。
- 全量 parity(1D/4H/8H/1W、全 174)`FAIL=0`。
- 1W 已纳入 official + combined summary,旧 Node 1W 不再混入。
- `verification-log.md` 有这次"全量对账通过"的真实记录——**这才是 cutover 真正合闸**。
