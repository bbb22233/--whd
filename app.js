const API_BASE = "http://127.0.0.1:8000";
const DEFAULT_INSTRUMENT = "BTC-USDT";
const DEFAULT_BAR = "1D";
const SUPPORTED_BARS = ["1D", "4H", "8H", "1W"];
const SYMBOL_PATTERN = /^[A-Z0-9]+-[A-Z0-9]+$/;
const DEFAULT_SYMBOLS = [
  "BTC-USDT",
  "ETH-USDT",
  "SOL-USDT",
  "BNB-USDT",
  "XRP-USDT",
  "DOGE-USDT",
  "ADA-USDT",
  "LINK-USDT",
  "AVAX-USDT",
  "TON-USDT",
  "TRX-USDT",
  "DOT-USDT",
  "BCH-USDT",
  "LTC-USDT",
  "UNI-USDT",
  "AAVE-USDT",
  "NEAR-USDT",
  "OP-USDT",
  "ARB-USDT",
  "SUI-USDT",
  "APT-USDT",
  "FIL-USDT",
  "ETC-USDT",
  "ATOM-USDT",
  "INJ-USDT",
  "STX-USDT",
  "IMX-USDT",
  "WLD-USDT",
  "AR-USDT",
  "XLM-USDT",
  "ICP-USDT",
  "HBAR-USDT",
  "ALGO-USDT",
  "LDO-USDT",
  "CRV-USDT",
  "ENS-USDT",
  "PENDLE-USDT",
  "JUP-USDT",
  "PYTH-USDT",
  "TIA-USDT",
  "ONDO-USDT",
  "FET-USDT",
  "PEPE-USDT",
  "SHIB-USDT",
  "BONK-USDT",
  "FLOKI-USDT",
  "WIF-USDT",
  "ORDI-USDT",
  "SATS-USDT",
  "NOT-USDT",
  "ENA-USDT",
  "W-USDT",
  "STRK-USDT",
  "ZK-USDT",
  "ZRO-USDT",
  "GALA-USDT",
  "SAND-USDT",
  "MANA-USDT",
];

const apiReport = (name, fallback) => ({
  primary: `${API_BASE}/api/reports/${name}`,
  fallback,
});

const $ = (selector) => document.querySelector(selector);

function normalizeInstrument(value) {
  if (!value) return null;
  const symbol = String(value).trim().toUpperCase().replaceAll("_", "-").replaceAll("/", "-");
  if (!symbol) return null;
  const normalized = !symbol.includes("-") && symbol.endsWith("USDT") ? `${symbol.slice(0, -4)}-USDT` : symbol;
  return SYMBOL_PATTERN.test(normalized) ? normalized : null;
}

function normalizeBar(value) {
  if (!value) return null;
  const bar = String(value).trim().toUpperCase();
  if (bar === "1") return "1D";
  return SUPPORTED_BARS.includes(bar) ? bar : null;
}

function reportPrefix(instrument, bar) {
  return `${instrument.replaceAll("-", "_")}_${bar}`;
}

function buildPaths(instrument, bar) {
  const prefix = reportPrefix(instrument, bar);
  const encodedInstrument = encodeURIComponent(instrument);
  const encodedBar = encodeURIComponent(bar);
  return {
    dashboard: `${API_BASE}/api/dashboard/current?instrument=${encodedInstrument}&bar=${encodedBar}`,
    weather: apiReport(`${prefix}_market_weather_router.json`, `./reports/${prefix}_market_weather_router.json`),
    features: apiReport(`${prefix}_feature_factory.json`, `./reports/${prefix}_feature_factory.json`),
    deviations: apiReport(`${prefix}_deviation_rules.json`, `./reports/${prefix}_deviation_rules.json`),
    candles: {
      primary: `${API_BASE}/api/candles/${encodedInstrument}/${encodedBar}`,
      fallback: `./data/clean/${prefix}_clean.json`,
    },
  };
}

function scopeFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return {
    instrument: normalizeInstrument(params.get("instrument")) || DEFAULT_INSTRUMENT,
    bar: normalizeBar(params.get("bar")) || DEFAULT_BAR,
  };
}

let currentScope = scopeFromUrl();
let PATHS = buildPaths(currentScope.instrument, currentScope.bar);
let renderToken = 0;

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatPct(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return `${Number(value).toFixed(digits)}%`;
}

function formatSignedPct(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const num = Number(value);
  const sign = num > 0 ? "+" : "";
  return `${sign}${num.toFixed(digits)}%`;
}

function signedClass(value) {
  const num = Number(value);
  if (num > 0) return "positive";
  if (num < 0) return "negative";
  return "neutral";
}

function gateClass(gate) {
  if (!gate) return "gate-neutral";
  if (gate.includes("红")) return gate.includes("黄") ? "gate-orange" : "gate-red";
  if (gate.includes("黄")) return "gate-yellow";
  if (gate.includes("绿")) return "gate-green";
  return "gate-neutral";
}

async function fetchJson(source, optional = false) {
  const candidates = typeof source === "string" ? [source] : [source.primary, source.fallback].filter(Boolean);
  let lastError = null;

  for (const path of candidates) {
    try {
      const response = await fetch(path, { cache: "no-store" });
      if (!response.ok) throw new Error(`${path} ${response.status}`);
      return response.json();
    } catch (error) {
      lastError = error;
    }
  }

  if (optional) return null;
  throw lastError ?? new Error("No data source available");
}

async function fetchLegacyDashboardData(paths) {
  const [weather, features, deviations, candles] = await Promise.all([
    fetchJson(paths.weather),
    fetchJson(paths.features),
    fetchJson(paths.deviations, true),
    fetchJson(paths.candles, true),
  ]);

  return { weather, features, deviations, candles, sourceMode: "legacy_files" };
}

async function fetchDashboardData(paths = PATHS) {
  try {
    const payload = await fetchJson(paths.dashboard);
    return {
      weather: payload.weather,
      features: payload.features,
      deviations: payload.deviations,
      candles: payload.candles,
      sources: payload.sources,
      sourceMode: "dashboard_api",
    };
  } catch (error) {
    console.warn("Dashboard API failed; falling back to legacy JSON files", error);
    return fetchLegacyDashboardData(paths);
  }
}

function setText(selector, text) {
  const node = $(selector);
  if (node) node.textContent = text ?? "--";
}

function makeMetaChip(label, value) {
  return `<span class="meta-chip">${label}: <strong>${value}</strong></span>`;
}

function getCurrentCandle(candlesPayload, date) {
  const candles = candlesPayload?.candles ?? [];
  const index = candles.findIndex((row) => row.date === date);
  const finalIndex = index >= 0 ? index : candles.length - 1;
  return {
    current: candles[finalIndex],
    previous: finalIndex > 0 ? candles[finalIndex - 1] : null,
    metadata: candlesPayload?.metadata ?? {},
  };
}

function renderQuoteGrid(candle, previousClose, values) {
  const dailyChange = candle && previousClose ? (candle.close / previousClose - 1) * 100 : null;
  const intradayChange = candle ? (candle.close / candle.open - 1) * 100 : null;
  setText("#lastPrice", formatNumber(candle?.close, 2));
  const changeNode = $("#dailyChange");
  if (changeNode) {
    changeNode.textContent = formatSignedPct(dailyChange);
    changeNode.className = `change-chip ${signedClass(dailyChange)}`;
  }

  const rows = [
    ["开盘", formatNumber(candle?.open, 2)],
    ["最高", formatNumber(candle?.high, 2)],
    ["最低", formatNumber(candle?.low, 2)],
    ["日内", formatSignedPct(intradayChange)],
    ["振幅", formatPct(values?.rangePct)],
    ["成交额", formatNumber(candle?.volume, 0)],
  ];

  $("#quoteGrid").innerHTML = rows
    .map(
      ([label, value]) => `
        <div class="quote-cell">
          <span class="cell-label">${label}</span>
          <span class="cell-value">${value}</span>
        </div>
      `,
    )
    .join("");
}

function renderOverview(weather, candleMeta) {
  const current = weather.current;
  const metadata = weather.metadata ?? {};
  setText("#instrument", metadata.instrument);
  setText("#bar", metadata.bar);
  setText("#gateText", current.gate);
  setText("#topRoute", `${current.topWeatherRoute} ${formatNumber(current.topWeatherScore, 2)}`);
  setText("#weatherSummary", current.weatherSummary);
  setText("#actionBias", current.actionBias);

  const gatePanel = $("#gatePanel");
  gatePanel.className = `gate-panel ${gateClass(current.gate)}`;

  $("#topMeta").innerHTML = [
    makeMetaChip("日期", current.date),
    makeMetaChip("样本", `${metadata.snapshotCount} 根`),
    makeMetaChip("数据", `${candleMeta.source ?? "--"} ${candleMeta.firstDate ?? metadata.firstDate} → ${metadata.lastDate}`),
  ].join("");

  const generatedAt = metadata.generatedAt
    ? new Date(metadata.generatedAt).toLocaleString("zh-CN", { hour12: false })
    : "--";
  setText("#footerLine", `${metadata.routerPrinciple} | generatedAt: ${generatedAt}`);
}

function horizonRows(rows, horizon = 5) {
  return (rows ?? []).filter((row) => Number(row.horizon) === horizon);
}

function componentByName(rows, name, horizon = 5) {
  return horizonRows(rows, horizon).find((row) => row.component === name);
}

function renderComponentGrid(weather, deviations) {
  const current = weather.current;
  const rows = weather.currentComponentRows ?? [];
  const middleRule = (deviations?.currentRuleRows ?? []).find(
    (row) => row.kindKey === "middle" && Number(row.horizon) === 10,
  );
  const maRule = (deviations?.currentRuleRows ?? []).find(
    (row) => row.kindKey === "ma233" && Number(row.horizon) === 10,
  );

  const cards = [
    {
      title: "波动状态",
      state: current.volatilityState,
      main: `降波 ${formatPct(current.fiveDayAtrDownProbabilityPct)}`,
      sub: `升波 ${formatPct(current.fiveDayAtrUpProbabilityPct)}`,
    },
    {
      title: "波动超额",
      state: current.remainingMomentumState,
      main: `${formatNumber(current.remainingMomentumAtr, 2)} ATR`,
      sub: `转正 ${formatPct(current.fiveDayFutureMomentumPositivePct)}`,
    },
    {
      title: "短ATR",
      state: current.shortAtrState,
      main: `3/21 ${formatNumber(current.atr3To21, 2)}`,
      sub: `8/21 ${formatNumber(current.atr8To21, 2)}`,
    },
    {
      title: "短期位置",
      state: current.middleState,
      main: `${formatNumber(current.middleDeviationAtr, 2)} ATR`,
      sub: `回归 ${formatPct(middleRule?.returnCloserProbabilityPct ?? current.middleTenDayReturnCloserPct)}`,
    },
    {
      title: "大周期过滤",
      state: current.maState,
      main: `${formatNumber(current.maDeviationAtr, 2)} ATR`,
      sub: `远离 ${formatPct(maRule?.continueAwayProbabilityPct ?? current.maTenDayContinueAwayPct)}`,
    },
    {
      title: "趋势 / 量能",
      state: `${current.trendState} / ${current.volumeState}`,
      main: `共振 ${current.resonanceCount ?? "--"} 周期`,
      sub: `量能 ${formatNumber(current.volumeMultiple, 2)}x`,
    },
  ];

  $("#componentGrid").innerHTML = cards
    .map(
      (card) => `
        <article class="component-card">
          <div class="component-title">${card.title}</div>
          <div class="component-state">${card.state}</div>
          <div class="component-kv"><span>${card.main}</span><strong>${card.sub}</strong></div>
        </article>
      `,
    )
    .join("");
}

function renderScores(scores) {
  const maxScore = Math.max(...scores.map((row) => Number(row.score) || 0), 100);
  $("#scoreList").innerHTML = scores
    .map((row, index) => {
      const width = Math.max(0, Math.min(100, ((Number(row.score) || 0) / maxScore) * 100));
      const color = index === 0 ? "var(--orange)" : index === 1 ? "var(--blue)" : "var(--cyan)";
      return `
        <div class="score-row">
          <div class="score-name">${row.label}</div>
          <div class="score-track"><div class="score-fill" style="width:${width}%; background:${color}"></div></div>
          <div class="score-value">${formatNumber(row.score, 2)}</div>
        </div>
      `;
    })
    .join("");
}

function renderMetrics(values) {
  const metrics = [
    ["ATR", formatPct(values.atrPct), `百分位 ${formatPct(values.atrPercentile)}`],
    ["振幅/ATR", formatNumber(values.volatilityMultiple, 2), `百分位 ${formatPct(values.volatilityMultiplePercentile)}`],
    ["波动超额", `${formatNumber(values.remainingMomentumAtr, 2)} ATR`, formatPct(values.remainingMomentumPct)],
    ["量能倍率", `${formatNumber(values.volumeMultiple, 2)}x`, "当前 / 20日均量"],
    ["8日涨跌", formatSignedPct(values.d8), "短端动量"],
    ["13日涨跌", formatSignedPct(values.d13), "中短动量"],
    ["21日涨跌", formatSignedPct(values.d21), "中端动量"],
    ["34日涨跌", formatSignedPct(values.d34), "惯性动量"],
    ["中值乖离率", formatSignedPct(values.middleDeviationRate), `${formatNumber(values.middleDeviationAtr, 2)} ATR`],
    ["中值位置", formatPct(values.middlePositionPct), "峰谷区间位置"],
    ["233MA乖离率", formatSignedPct(values.maDeviationRate), `${formatNumber(values.maDeviationAtr, 2)} ATR`],
    ["233MA位置", formatPct(values.maPositionPct), "大周期峰谷位置"],
    ["趋势动能", formatNumber(values.trendScore, 2), `${values.resonanceCount ?? "--"} 周期同向`],
    ["拉伸热度", formatPct(values.stretchHeat), "位置百分位合成"],
  ];

  $("#metricGrid").innerHTML = metrics
    .map(([label, value, sub]) => {
      const rawValue = String(value);
      const signClass = rawValue.startsWith("+") ? "positive" : rawValue.startsWith("-") ? "negative" : "";
      return `
        <div class="metric-cell">
          <span class="cell-label">${label}</span>
          <span class="cell-value ${signClass}">${value}</span>
          <span class="cell-label">${sub}</span>
        </div>
      `;
    })
    .join("");
}

function renderFibTable(values) {
  const periods = [3, 8, 13, 21];
  const rows = periods.map((period) => ({
    period,
    atrPct: values[`atr${period}Pct`],
    atrRank: values[`atr${period}Percentile`],
    volatilityMultiple: values[`volatilityMultiple${period}`] ?? values.volatilityMultiple,
    volatilityRank: values[`volatilityMultiple${period}Percentile`] ?? values.volatilityMultiplePercentile,
    remainingMomentum: values[`remainingMomentumAtr${period}`] ?? values.remainingMomentumAtr,
  }));

  $("#fibTable").innerHTML = `
    <thead>
      <tr>
        <th>周期</th>
        <th>ATR%</th>
        <th>ATR百分位</th>
        <th>振幅/ATR</th>
        <th>振幅倍率百分位</th>
        <th>波动超额ATR</th>
      </tr>
    </thead>
    <tbody>
      ${rows
        .map(
          (row) => `
            <tr>
              <td>${row.period}日</td>
              <td>${formatPct(row.atrPct)}</td>
              <td>${formatPct(row.atrRank)}</td>
              <td>${formatNumber(row.volatilityMultiple, 2)}</td>
              <td>${formatPct(row.volatilityRank)}</td>
              <td class="${signedClass(row.remainingMomentum)}">${formatNumber(row.remainingMomentum, 2)}</td>
            </tr>
          `,
        )
        .join("")}
    </tbody>
  `;
}

function renderComponentTable(rows) {
  const selected = horizonRows(rows, 5);
  $("#componentTable").innerHTML = `
    <thead>
      <tr>
        <th>指标</th>
        <th>状态</th>
        <th>置信度</th>
        <th>样本</th>
        <th>ATR升</th>
        <th>ATR降</th>
        <th>振幅超ATR</th>
        <th>中位ATR变化</th>
      </tr>
    </thead>
    <tbody>
      ${selected
        .map(
          (row) => `
            <tr>
              <td>${row.component}</td>
              <td>${row.state}</td>
              <td>${formatPct(row.currentConfidencePct)}</td>
              <td>${formatNumber(row.occurrences, 0)}</td>
              <td>${formatPct(row.atrUpProbabilityPct)}</td>
              <td>${formatPct(row.atrDownProbabilityPct)}</td>
              <td>${formatPct(row.futureRemainingMomentumPositivePct)}</td>
              <td class="${signedClass(row.medianAtrChangePct)}">${formatSignedPct(row.medianAtrChangePct)}</td>
            </tr>
          `,
        )
        .join("")}
    </tbody>
  `;
}

function renderDeviationTable(rows) {
  const selected = (rows ?? []).filter((row) => [1, 3, 5, 10].includes(Number(row.horizon)));
  $("#deviationTable").innerHTML = `
    <thead>
      <tr>
        <th>指标</th>
        <th>周期</th>
        <th>状态</th>
        <th>乖离率</th>
        <th>ATR乖离</th>
        <th>位置%</th>
        <th>回归</th>
        <th>继续远离</th>
        <th>置信</th>
      </tr>
    </thead>
    <tbody>
      ${selected
        .map(
          (row) => `
            <tr>
              <td>${row.kind}</td>
              <td>${row.horizon}日</td>
              <td>${row.state}</td>
              <td class="${signedClass(row.deviationRate)}">${formatSignedPct(row.deviationRate)}</td>
              <td class="${signedClass(row.deviationAtr)}">${formatNumber(row.deviationAtr, 2)}</td>
              <td>${formatPct(row.positionPct)}</td>
              <td>${formatPct(row.returnCloserProbabilityPct)}</td>
              <td>${formatPct(row.continueAwayProbabilityPct)}</td>
              <td>${row.confidence}</td>
            </tr>
          `,
        )
        .join("")}
    </tbody>
  `;
}

function renderNotes(weather, features, deviations) {
  const current = weather.current;
  const values = features.current?.values ?? {};
  const deviationWeather = deviations?.finalWeather;
  const notes = [
    ["主结论", `${current.gate}，当前更像“${current.topWeatherRoute}”天气，分数 ${formatNumber(current.topWeatherScore, 2)}。`],
    ["波动", `ATR 处在 ${formatPct(values.atrPercentile)} 分位，振幅/ATR 为 ${formatNumber(values.volatilityMultiple, 2)}，历史上 5 日后 ATR 降低概率 ${formatPct(current.fiveDayAtrDownProbabilityPct)}。`],
    ["波动超额", `波动超额 ${formatNumber(values.remainingMomentumAtr, 2)} ATR，属于 ${current.remainingMomentumState}，5 日后振幅超ATR概率 ${formatPct(current.fiveDayFutureMomentumPositivePct)}。`],
    ["乖离", `中值乖离率 ${formatSignedPct(values.middleDeviationRate)}，等于 ${formatNumber(values.middleDeviationAtr, 2)} 个 ATR；233MA 乖离率 ${formatSignedPct(values.maDeviationRate)}，等于 ${formatNumber(values.maDeviationAtr, 2)} 个 ATR。`],
    ["规则", deviationWeather?.riskNote ?? "当前规则只做天气识别，不单独触发交易。"],
  ];

  $("#noteList").innerHTML = notes
    .map(([title, text]) => `<div class="note-item"><strong>${title}</strong> ${text}</div>`)
    .join("");
}

function clearDashboardSections() {
  const emptyNodes = [
    "#quoteGrid",
    "#componentGrid",
    "#scoreList",
    "#metricGrid",
    "#componentTable",
    "#deviationTable",
    "#noteList",
    "#fibTable",
  ];
  emptyNodes.forEach((selector) => {
    const node = $(selector);
    if (node) node.innerHTML = "";
  });
  setText("#lastPrice", "--");
  const changeNode = $("#dailyChange");
  if (changeNode) {
    changeNode.textContent = "--";
    changeNode.className = "change-chip neutral";
  }
}

function renderInsufficient(metadata) {
  setText("#instrument", metadata?.instrument ?? "--");
  setText("#bar", metadata?.bar ?? "--");
  setText("#gateText", "样本不足");
  setText("#topRoute", "--");
  const panel = $("#gatePanel");
  if (panel) panel.className = "gate-panel gate-neutral";
  setText("#weatherSummary", "历史数据不足，暂不输出灯号");
  setText("#actionBias", "等待历史补齐");
  $("#topMeta").innerHTML = [
    makeMetaChip("数据", metadata?.dataStatus ?? "insufficient_history"),
    makeMetaChip("样本", metadata?.snapshotCount ?? "--"),
  ].join("");
  setText("#footerLine", "current is empty; frontend rendered an insufficient-history state");
  clearDashboardSections();
}

function ensureOption(select, value) {
  if (!select || !value) return;
  const exists = Array.from(select.options).some((option) => option.value === value);
  if (!exists) {
    select.append(new Option(value, value));
  }
}

function syncControls() {
  setText("#instrument", currentScope.instrument);
  setText("#bar", currentScope.bar);

  const symbolSelect = $("#symbolSelect");
  if (symbolSelect) {
    ensureOption(symbolSelect, currentScope.instrument);
    symbolSelect.value = currentScope.instrument;
  }

  const barSelect = $("#barSelect");
  if (barSelect) {
    barSelect.value = currentScope.bar;
  }
}

function updateUrlFromScope() {
  const url = new URL(window.location.href);
  url.searchParams.set("instrument", currentScope.instrument);
  url.searchParams.set("bar", currentScope.bar);
  window.history.pushState({ ...currentScope }, "", url);
}

function setScope(instrument, bar, { push = false } = {}) {
  currentScope = {
    instrument: normalizeInstrument(instrument) || DEFAULT_INSTRUMENT,
    bar: normalizeBar(bar) || DEFAULT_BAR,
  };
  PATHS = buildPaths(currentScope.instrument, currentScope.bar);
  syncControls();
  if (push) updateUrlFromScope();
}

function symbolListFromPayload(payload) {
  const symbols = Array.isArray(payload?.symbols) ? payload.symbols : [];
  return Array.from(new Set(symbols.map(normalizeInstrument).filter(Boolean)));
}

function renderSymbolOptions(symbols) {
  const symbolSelect = $("#symbolSelect");
  if (!symbolSelect) return;
  const options = Array.from(new Set([currentScope.instrument, ...symbols].map(normalizeInstrument).filter(Boolean)));
  symbolSelect.innerHTML = "";
  options.forEach((symbol) => {
    symbolSelect.append(new Option(symbol, symbol));
  });
  symbolSelect.disabled = options.length <= 1;
  syncControls();
}

async function loadSymbols() {
  try {
    const response = await fetch(`${API_BASE}/api/market/symbols`, { cache: "no-store" });
    if (!response.ok) throw new Error(`symbols ${response.status}`);
    const symbols = symbolListFromPayload(await response.json());
    return symbols.length ? symbols : DEFAULT_SYMBOLS;
  } catch (error) {
    console.warn("Market symbols API failed; using built-in symbols", error);
    return DEFAULT_SYMBOLS;
  }
}

function setupSelectors() {
  renderSymbolOptions(DEFAULT_SYMBOLS);

  const symbolSelect = $("#symbolSelect");
  const barSelect = $("#barSelect");
  const handleChange = () => {
    setScope(symbolSelect?.value, barSelect?.value, { push: true });
    renderDashboard().catch(handleDashboardError);
  };

  symbolSelect?.addEventListener("change", handleChange);
  barSelect?.addEventListener("change", handleChange);
  window.addEventListener("popstate", () => {
    const nextScope = scopeFromUrl();
    setScope(nextScope.instrument, nextScope.bar);
    renderDashboard().catch(handleDashboardError);
  });

  loadSymbols().then(renderSymbolOptions).catch((error) => {
    console.warn("Unable to load market symbols", error);
  });
}

function handleDashboardError(error) {
  console.error(error);
  renderInsufficient({
    instrument: currentScope.instrument,
    bar: currentScope.bar,
    dataStatus: "report_missing",
    snapshotCount: "--",
  });
}

async function renderDashboard() {
  const token = ++renderToken;
  const scope = { ...currentScope };
  const paths = PATHS;
  syncControls();
  setText("#weatherSummary", "数据加载中...");
  let payload;
  try {
    payload = await fetchDashboardData(paths);
  } catch (error) {
    if (token !== renderToken) return;
    console.warn("Dashboard data unavailable; rendering insufficient state", error);
    renderInsufficient({ instrument: scope.instrument, bar: scope.bar, dataStatus: "report_missing", snapshotCount: "--" });
    return;
  }

  if (token !== renderToken) return;
  const { weather, features, deviations, candles } = payload;

  if (!weather?.current) {
    renderInsufficient(weather?.metadata ?? { instrument: scope.instrument, bar: scope.bar, dataStatus: "insufficient_history" });
    return;
  }

  const values = features.current?.values ?? {};
  const { current: candle, previous, metadata: candleMeta } = getCurrentCandle(candles, weather.current.date);

  renderOverview(weather, candleMeta);
  renderQuoteGrid(candle, previous?.close, values);
  renderComponentGrid(weather, deviations);
  renderScores(weather.strategyScores ?? []);
  renderMetrics(values);
  renderFibTable(values);
  renderComponentTable(weather.currentComponentRows ?? []);
  renderDeviationTable(deviations?.currentRuleRows ?? []);
  renderNotes(weather, features, deviations);
}

$("#reloadButton").addEventListener("click", () => {
  renderDashboard().catch(handleDashboardError);
});

setupSelectors();
renderDashboard().catch(handleDashboardError);
