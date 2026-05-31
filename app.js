const PATHS = {
  weather: "./reports/BTC_USDT_1D_market_weather_router.json",
  features: "./reports/BTC_USDT_1D_feature_factory.json",
  deviations: "./reports/BTC_USDT_1D_deviation_rules.json",
  candles: "./data/clean/BTC_USDT_1D_clean.json",
};

const $ = (selector) => document.querySelector(selector);

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

async function fetchJson(path, optional = false) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    if (optional) return null;
    throw new Error(`${path} ${response.status}`);
  }
  return response.json();
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
  changeNode.textContent = formatSignedPct(dailyChange);
  changeNode.className = `change-chip ${signedClass(dailyChange)}`;

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
  const metadata = weather.metadata;
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
    (row) => row.kindKey === "ma" && Number(row.horizon) === 10,
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

async function renderDashboard() {
  setText("#weatherSummary", "数据加载中...");
  const [weather, features, deviations, candles] = await Promise.all([
    fetchJson(PATHS.weather),
    fetchJson(PATHS.features),
    fetchJson(PATHS.deviations, true),
    fetchJson(PATHS.candles),
  ]);

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
  renderDashboard().catch((error) => {
    console.error(error);
    setText("#weatherSummary", `加载失败: ${error.message}`);
  });
});

renderDashboard().catch((error) => {
  console.error(error);
  setText("#weatherSummary", `加载失败: ${error.message}`);
});
