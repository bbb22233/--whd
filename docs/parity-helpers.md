# 跨语言对平助手(Parity Helpers)留痕

> 留痕文档。记录 Python 复刻 Node 行为时,为达到**逐字节对平(`FAIL=0`)**而必须引入的 3 个数值/字符串助手 + 1 个序列化约定。
> 实现位置:`backend_py/research/feature_factory.py`(被 `deviation_rules.py` / `market_weather_router.py` / `summary.py` / `clean.py` / `macro_data.py` 复用)。
> 背景:Python official 全周期对 Node `FAIL=0`,靠的就是下面这几条——**它们不是优化,是为了和 JS 的"怪癖"完全一致**。

---

## 1. `js_round` — 复刻 JS `Number.toFixed` 的四舍五入

```python
def js_round(value, digits=4):
    if not finite(value):
        return 0
    from decimal import Decimal, ROUND_HALF_UP
    quant = Decimal(1).scaleb(-digits)
    return float(Decimal(float(value)).quantize(quant, rounding=ROUND_HALF_UP))
```

- **为什么**:不能用 `floor(x*10**d + 0.5) / 10**d`。该写法在 `.xx5` 边界因浮点表示误差会与 JS `toFixed` **分叉**。
- **真实事故**:`SOL 8H medianPositionPct` Python 算出 `50.48`、Node 是 `50.49`。根因就是 `floor(x*100+0.5)`。
- **修法**:走 `Decimal(float(value))` + `ROUND_HALF_UP`,与 JS `toFixed` 的半值进位一致。

## 2. `js_sum` — 朴素左到右累加,**禁用** Python 的补偿求和

```python
def js_sum(values):
    total = 0.0
    for value in values:
        total += value
    return total
```

- **为什么**:Python 3.12+ 内置 `sum()` 用 **Neumaier/Kahan 补偿求和**,精度比 JS `Array.reduce((a,b)=>a+b,0)` 的朴素累加更高 → 反而和 Node **对不上**。
- **真实事故**:`DOGE 4H featureStats` 的 mean/std 因 `sum()` 补偿求和而与 Node 分叉。
- **修法**:手写朴素 `total += value` 左累加,刻意"放弃"精度以匹配 JS。`average()` 也走 `js_sum`。

## 3. `js_number_to_string` — 复刻 JS 模板字符串 `${num}` 丢掉 `.0`

```python
def js_number_to_string(value):
    if not finite(value):
        return str(value)
    number = float(value)
    integer = int(number)
    return str(integer) if number == integer else repr(number)
```

- **为什么**:JS `` `${30}` `` → `"30"`,而 Python `f"{30.0}"` → `"30.0"`。整数值的浮点要去掉 `.0`。
- **真实事故**:`market_weather_router` 的 `confidenceGateReason` 里 Python 写 `"30.0"`、Node 写 `"30"` → 1W 对账 `FAIL`。
- **修法**:整数值用 `str(int(...))`,非整数用 `repr(...)`(`repr` 给出 JS 风格最短往返表示)。

## 4. 序列化约定 — `None` 键要**省略**,不写 `null`

- **为什么**:JS `JSON.stringify` 会**丢掉值为 `undefined` 的键**;Python `json.dumps` 默认把 `None` 写成 `null`。两者对账会因"键存在与否"分叉。
- **真实事故**:`current=null`(历史不足)的品种,Node 整组 weather 键被省略,Python 却写了一堆 `null` → 键集合不等 → `FAIL`。
- **修法**:`summary.build_summary_row`(`summary.py`)在 `current` 为空时**只省略 `current.*` 那一组 weather 键**,而**不是**全局删所有 `None`。
  - ⚠️ **护栏**:不要图省事全局删 `None` —— 会误删合法的 `null` 字段。只针对"该被 JS undefined 省略"的那组键。

---

## 对账怎么验
- 一键回归:`backend_py/run_parity_check.py`(N1)——Node 重生成 golden → Python `_py` 影子 → 逐字段比 → `finally` 还原 official。
- 容差:`VALUE_TOLERANCE=1e-3`,递归比对**全键集合**,只忽略时间戳。
- 任何一条助手回退到"更聪明/更精确"的写法,都会让对账重新 `FAIL` —— **这些助手必须保持"和 JS 一样笨"**。

## 退役后注意
- 砍掉 Node 后(见 `node-retirement-checklist.md`),对账基准从"现场跑 Node"换成"冻结 golden 快照"(N7);
  但**这些助手仍要保留**——它们已经把 JS 的数值行为固化进 Python official 产物里,改动它们会改变产物本身。
