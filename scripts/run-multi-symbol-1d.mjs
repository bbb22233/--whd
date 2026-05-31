import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs, reportStem } from "../backtest/config.mjs";
import { barToMs, candlesToCsvRows, cleanOkxRaw, formatCandleDate } from "../backtest/clean.mjs";
import { buildDeviationRules } from "../backtest/deviation-rules.mjs";
import { runDeviationStudy } from "../backtest/deviation-study.mjs";
import { buildFeatureFactory } from "../backtest/feature-factory.mjs";
import { buildMarketWeatherRouter } from "../backtest/market-weather-router.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";
import { downloadOkxHistory } from "../backtest/okx.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));

const defaultSpotSymbols = [
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
  "MANA-USDT"
];

const derivedBars = new Map([
  ["8H", { sourceBar: "4H", groupSize: 2 }]
]);

function parseBatchArgs(argv) {
  const config = parseArgs(argv, {
    ...defaultConfig,
    instrument: "BTC-USDT",
    bar: "1D",
    days: 3650
  });

  let symbols = defaultSpotSymbols;
  let bars = [config.bar];
  let skipDownload = false;
  let summaryOnly = false;
  let fromReports = false;

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];

    if (arg === "--symbols") {
      const values = collectOptionValues(argv, index + 1);
      symbols = splitCsvValues(values);
      index += values.length;
    } else if (arg === "--bars") {
      const values = collectOptionValues(argv, index + 1);
      bars = splitCsvValues(values).map(normalizeBar).filter(Boolean);
      index += values.length;
    } else if (arg === "--skip-download") {
      skipDownload = true;
    } else if (arg === "--summary-only") {
      summaryOnly = true;
    } else if (arg === "--from-reports") {
      fromReports = true;
    }
  }

  return {
    config,
    symbols: [...new Set(symbols)],
    bars: [...new Set(bars)],
    skipDownload,
    summaryOnly,
    fromReports
  };
}

function collectOptionValues(argv, startIndex) {
  const values = [];

  for (let index = startIndex; index < argv.length; index += 1) {
    const value = argv[index];
    if (String(value).startsWith("--")) break;
    values.push(value);
  }

  return values;
}

function splitCsvValues(values) {
  return values.flatMap((value) => String(value).split(","))
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeBar(value) {
  const bar = String(value).trim();
  if (bar === "1") return "1D";
  return bar;
}

function createSymbolConfig(baseConfig, instrument) {
  return {
    ...structuredClone(baseConfig),
    instrument
  };
}

function createBarConfig(baseConfig, bar) {
  return {
    ...structuredClone(baseConfig),
    bar
  };
}

function derivedBarConfig(config) {
  const recipe = derivedBars.get(config.bar);
  if (!recipe) return null;
  return {
    ...recipe,
    sourceConfig: {
      ...structuredClone(config),
      bar: recipe.sourceBar
    }
  };
}

function round(value, digits = 4) {
  if (!Number.isFinite(Number(value))) return null;
  return Number(Number(value).toFixed(digits));
}

function scoreColumns(strategyScores) {
  return Object.fromEntries(
    (strategyScores ?? []).map((row) => [`score_${row.key}`, row.score])
  );
}

function historyQuality(config, cleanRows, hasCurrent) {
  if (!hasCurrent || cleanRows < config.indicator.maPeriod) {
    return { dataStatus: "insufficient_history", historyQuality: "insufficient", periodWeight: 0 };
  }

  if (config.bar === "1W") {
    if (cleanRows <= 300) return { dataStatus: "ok", historyQuality: "weak_display_only", periodWeight: 0 };
    if (cleanRows <= 364) return { dataStatus: "ok", historyQuality: "half_weight", periodWeight: 0.5 };
    return { dataStatus: "ok", historyQuality: "full_weight", periodWeight: 1 };
  }

  return { dataStatus: "ok", historyQuality: "full_weight", periodWeight: 1 };
}

async function readJsonIfExists(filePath) {
  try {
    return await readJson(filePath);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

function missingBars(candles, bar) {
  const barMs = barToMs(bar);
  const rows = [];

  for (let index = 1; index < candles.length; index += 1) {
    const gap = candles[index].openTime - candles[index - 1].openTime;
    if (gap > barMs * 1.5) {
      rows.push({
        previousDate: candles[index - 1].date,
        nextDate: candles[index].date,
        missingBars: Math.round(gap / barMs) - 1
      });
    }
  }

  return rows;
}

function aggregateCandles(sourceCandles, targetBar, groupSize) {
  const targetMs = barToMs(targetBar);
  const sourceMs = targetMs / groupSize;
  const buckets = new Map();

  for (const candle of sourceCandles) {
    const bucketOpen = Math.floor(candle.openTime / targetMs) * targetMs;
    const bucket = buckets.get(bucketOpen) ?? [];
    bucket.push(candle);
    buckets.set(bucketOpen, bucket);
  }

  return Array.from(buckets.entries())
    .sort(([left], [right]) => left - right)
    .flatMap(([openTime, bucket]) => {
      const sorted = bucket.sort((left, right) => left.openTime - right.openTime);
      if (sorted.length !== groupSize) return [];

      for (let index = 1; index < sorted.length; index += 1) {
        if (sorted[index].openTime - sorted[index - 1].openTime !== sourceMs) return [];
      }

      return [{
        openTime,
        closeTime: openTime + targetMs - 1,
        date: formatCandleDate(openTime, targetBar),
        open: sorted[0].open,
        high: Math.max(...sorted.map((candle) => candle.high)),
        low: Math.min(...sorted.map((candle) => candle.low)),
        close: sorted.at(-1).close,
        volume: sorted.reduce((sum, candle) => sum + candle.volume, 0),
        confirm: "1"
      }];
    });
}

function deriveCleanPayload(sourceCleanPayload, config, recipe) {
  const candles = aggregateCandles(sourceCleanPayload.candles, config.bar, recipe.groupSize);
  const sourceMeta = sourceCleanPayload.metadata ?? {};

  return {
    metadata: {
      source: sourceMeta.source,
      sourceBar: recipe.sourceBar,
      instrument: config.instrument,
      bar: config.bar,
      requestedDays: config.days,
      downloadedAt: sourceMeta.downloadedAt,
      cleanedAt: new Date().toISOString(),
      rawRows: sourceMeta.cleanRows,
      cleanRows: candles.length,
      duplicateRows: 0,
      invalidRows: 0,
      unconfirmedRows: 0,
      missingBars: missingBars(candles, config.bar),
      firstDate: candles[0]?.date || null,
      lastDate: candles.at(-1)?.date || null,
      derivedFrom: recipe.sourceBar
    },
    candles
  };
}

function buildSummaryRow({ config, cleanPayload, featureResult, weatherResult, deviationRules }) {
  const current = weatherResult.current ?? {};
  const values = featureResult?.current?.values ?? {};
  const finalWeather = deviationRules.finalWeather ?? weatherResult.deviationFinalWeather ?? {};
  const cleanMeta = cleanPayload.metadata ?? {};
  const quality = historyQuality(config, cleanMeta.cleanRows ?? 0, Boolean(current.gate));

  return {
    instrument: config.instrument,
    bar: config.bar,
    dataStatus: quality.dataStatus,
    historyQuality: quality.historyQuality,
    periodWeight: quality.periodWeight,
    requiredWarmupBars: config.indicator.maPeriod,
    source: cleanMeta.source,
    firstDate: cleanMeta.firstDate,
    lastDate: cleanMeta.lastDate,
    cleanRows: cleanMeta.cleanRows,
    date: current.date,
    close: current.close,
    gate: current.gate,
    topWeatherRoute: current.topWeatherRoute,
    topWeatherScore: current.topWeatherScore,
    weatherSummary: current.weatherSummary,
    actionBias: current.actionBias,
    volatilityState: current.volatilityState,
    atrPct: current.atrPct,
    atrPercentile: current.atrPercentile,
    volatilityMultiple: current.volatilityMultiple,
    volatilityMultiplePercentile: current.volatilityMultiplePercentile,
    remainingMomentumAtr: current.remainingMomentumAtr,
    remainingMomentumState: current.remainingMomentumState,
    fiveDayAtrDownProbabilityPct: current.fiveDayAtrDownProbabilityPct,
    fiveDayAtrUpProbabilityPct: current.fiveDayAtrUpProbabilityPct,
    fiveDayFutureMomentumPositivePct: current.fiveDayFutureMomentumPositivePct,
    atr3Pct: round(values.atr3Pct ?? current.atr3Pct),
    atr8Pct: round(values.atr8Pct ?? current.atr8Pct),
    atr13Pct: round(values.atr13Pct ?? current.atr13Pct),
    atr21Pct: round(values.atr21Pct ?? current.atr21Pct),
    atr3To21: current.atr3To21,
    atr8To21: current.atr8To21,
    middleState: current.middleState,
    middleDeviationRate: current.middleDeviationRate,
    middleDeviationAtr: current.middleDeviationAtr,
    middlePositionPct: round(values.middlePositionPct ?? current.middlePositionPct),
    middleTenDayReturnCloserPct: current.middleTenDayReturnCloserPct,
    maState: current.maState,
    maDeviationRate: current.maDeviationRate,
    maDeviationAtr: current.maDeviationAtr,
    maPositionPct: round(values.maPositionPct ?? current.maPositionPct),
    maTenDayContinueAwayPct: current.maTenDayContinueAwayPct,
    trendState: current.trendState,
    trendScore: current.trendScore,
    resonanceDirection: current.resonanceDirection,
    resonanceCount: current.resonanceCount,
    volumeState: current.volumeState,
    volumeMultiple: current.volumeMultiple,
    deviationWeather: finalWeather.weather,
    deviationRiskNote: finalWeather.riskNote,
    ...scoreColumns(weatherResult.strategyScores)
  };
}

async function runOneSymbolFromReports(baseConfig, instrument) {
  const config = createSymbolConfig(baseConfig, instrument);
  const stem = fileStem(config);
  const reportName = reportStem(config);
  const cleanJsonPath = join(root, "data", "clean", `${stem}_clean.json`);
  const featureJsonPath = join(root, "reports", `${reportName}_feature_factory.json`);
  const deviationJsonPath = join(root, "reports", `${reportName}_deviation_rules.json`);
  const weatherJsonPath = join(root, "reports", `${reportName}_market_weather_router.json`);

  const cleanPayload = await readJson(cleanJsonPath);
  const weatherResult = await readJson(weatherJsonPath);
  const featureResult = await readJsonIfExists(featureJsonPath);
  const deviationRules = await readJsonIfExists(deviationJsonPath);

  return {
    summaryRow: buildSummaryRow({
      config,
      cleanPayload,
      featureResult,
      weatherResult,
      deviationRules: deviationRules ?? { finalWeather: weatherResult.deviationFinalWeather }
    }),
    outputs: {
      cleanJsonPath,
      featureJsonPath,
      deviationJsonPath,
      weatherJsonPath
    }
  };
}

async function runOneSymbol(baseConfig, instrument, options) {
  const config = createSymbolConfig(baseConfig, instrument);
  if (options.fromReports) return runOneSymbolFromReports(baseConfig, instrument);

  const derived = derivedBarConfig(config);
  const sourceConfig = derived?.sourceConfig ?? config;
  const stem = fileStem(config);
  const sourceStem = fileStem(sourceConfig);
  const reportName = reportStem(config);

  const rawPath = join(root, "data", "raw", `${sourceStem}_raw.json`);
  const cleanJsonPath = join(root, "data", "clean", `${stem}_clean.json`);
  const cleanCsvPath = join(root, "data", "clean", `${stem}_clean.csv`);
  const featureJsonPath = join(root, "reports", `${reportName}_feature_factory.json`);
  const deviationJsonPath = join(root, "reports", `${reportName}_deviation_rules.json`);
  const deviationCurrentCsvPath = join(root, "reports", `${reportName}_deviation_rules_current.csv`);
  const deviationLibraryCsvPath = join(root, "reports", `${reportName}_deviation_rule_library.csv`);
  const weatherJsonPath = join(root, "reports", `${reportName}_market_weather_router.json`);
  const weatherCurrentCsvPath = join(root, "reports", `${reportName}_market_weather_current.csv`);
  const weatherScoresCsvPath = join(root, "reports", `${reportName}_market_weather_scores.csv`);
  const weatherComponentsCsvPath = join(root, "reports", `${reportName}_market_weather_components_current.csv`);
  const weatherSummaryCsvPath = join(root, "reports", `${reportName}_market_weather_component_summary.csv`);

  const existingSourceRaw = derived && options.preferExistingSourceRaw
    ? await readJsonIfExists(rawPath)
    : null;
  const rawPayload = options.skipDownload
    ? await readJson(rawPath)
    : existingSourceRaw ?? await downloadOkxHistory(sourceConfig);

  await writeJson(rawPath, rawPayload);

  const sourceCleanPayload = cleanOkxRaw(rawPayload);
  const cleanPayload = derived
    ? deriveCleanPayload(sourceCleanPayload, config, derived)
    : sourceCleanPayload;
  await writeJson(cleanJsonPath, cleanPayload);
  await writeCsv(cleanCsvPath, candlesToCsvRows(cleanPayload.candles));

  let featureResult = null;
  let deviationRules = null;

  if (!options.summaryOnly) {
    featureResult = buildFeatureFactory(cleanPayload, config);
    await writeJson(featureJsonPath, {
      metadata: featureResult.metadata,
      features: featureResult.features,
      featureStats: featureResult.featureStats,
      current: featureResult.current
    });

    const deviationStudy = runDeviationStudy(cleanPayload, config);
    deviationRules = buildDeviationRules(deviationStudy);
    await writeJson(deviationJsonPath, deviationRules);
    await writeCsv(deviationCurrentCsvPath, deviationRules.currentRuleRows);
    await writeCsv(deviationLibraryCsvPath, deviationRules.ruleLibraryRows);
  }

  const weatherResult = buildMarketWeatherRouter(cleanPayload, config);
  await writeJson(weatherJsonPath, {
    metadata: weatherResult.metadata,
    current: weatherResult.current,
    strategyScores: weatherResult.strategyScores,
    deviationFinalWeather: weatherResult.deviationFinalWeather,
    currentComponentRows: weatherResult.currentComponentRows,
    componentSummaryRows: weatherResult.componentSummaryRows
  });
  await writeCsv(weatherCurrentCsvPath, weatherResult.current ? [weatherResult.current] : []);
  await writeCsv(weatherScoresCsvPath, weatherResult.strategyScores);
  await writeCsv(weatherComponentsCsvPath, weatherResult.currentComponentRows);
  await writeCsv(weatherSummaryCsvPath, weatherResult.componentSummaryRows);

  return {
    summaryRow: buildSummaryRow({
      config,
      cleanPayload,
      featureResult,
      weatherResult,
      deviationRules: deviationRules ?? { finalWeather: weatherResult.deviationFinalWeather }
    }),
    outputs: {
      rawPath,
      cleanJsonPath,
      cleanCsvPath,
      featureJsonPath,
      deviationJsonPath,
      weatherJsonPath
    }
  };
}

async function writeBarSummary({ config, symbols, rows, errors, skipDownload, summaryOnly, fromReports, startedAt }) {
  const outputStem = `multi_${config.bar}_market_weather_current`;
  const summaryJsonPath = join(root, "reports", `${outputStem}.json`);
  const summaryCsvPath = join(root, "reports", `${outputStem}.csv`);

  await writeJson(summaryJsonPath, {
    metadata: {
      symbols,
      bar: config.bar,
      days: config.days,
      skipDownload,
      summaryOnly,
      fromReports,
      startedAt: startedAt.toISOString(),
      finishedAt: new Date().toISOString(),
      successCount: rows.length,
      weatherCount: rows.filter((row) => row.dataStatus === "ok").length,
      insufficientHistoryCount: rows.filter((row) => row.dataStatus !== "ok").length,
      errorCount: errors.length
    },
    rows,
    errors
  });
  await writeCsv(summaryCsvPath, rows);

  return {
    bar: config.bar,
    summaryJsonPath,
    summaryCsvPath,
    successCount: rows.length,
    weatherCount: rows.filter((row) => row.dataStatus === "ok").length,
    insufficientHistoryCount: rows.filter((row) => row.dataStatus !== "ok").length,
    errorCount: errors.length
  };
}

async function writeCombinedSummary({ bars, symbols, rows, errors, skipDownload, summaryOnly, fromReports, startedAt }) {
  const summaryJsonPath = join(root, "reports", "multi_period_market_weather_current.json");
  const summaryCsvPath = join(root, "reports", "multi_period_market_weather_current.csv");

  await writeJson(summaryJsonPath, {
    metadata: {
      symbols,
      bars,
      skipDownload,
      summaryOnly,
      fromReports,
      startedAt: startedAt.toISOString(),
      finishedAt: new Date().toISOString(),
      successCount: rows.length,
      weatherCount: rows.filter((row) => row.dataStatus === "ok").length,
      insufficientHistoryCount: rows.filter((row) => row.dataStatus !== "ok").length,
      errorCount: errors.length
    },
    rows,
    errors
  });
  await writeCsv(summaryCsvPath, rows);

  return {
    summaryJsonPath,
    summaryCsvPath,
    successCount: rows.length,
    weatherCount: rows.filter((row) => row.dataStatus === "ok").length,
    insufficientHistoryCount: rows.filter((row) => row.dataStatus !== "ok").length,
    errorCount: errors.length
  };
}

const { config, symbols, bars, skipDownload, summaryOnly, fromReports } = parseBatchArgs(process.argv.slice(2));
const startedAt = new Date();
const allRows = [];
const allErrors = [];
const barSummaries = [];

for (const bar of bars) {
  const barStartedAt = new Date();
  const barConfig = createBarConfig(config, bar);
  const rows = [];
  const errors = [];

  for (const [index, symbol] of symbols.entries()) {
    const label = `${index + 1}/${symbols.length} ${symbol} ${barConfig.bar}`;
    console.log(`[multi-weather] ${label} start`);

    try {
      const result = await runOneSymbol(barConfig, symbol, {
        skipDownload,
        summaryOnly,
        fromReports,
        preferExistingSourceRaw: bars.includes("4H") && barConfig.bar === "8H"
      });
      rows.push(result.summaryRow);
      console.log(JSON.stringify({
        step: "multi-symbol-weather",
        instrument: symbol,
        bar: barConfig.bar,
        gate: result.summaryRow.gate,
        topWeatherRoute: result.summaryRow.topWeatherRoute,
        topWeatherScore: result.summaryRow.topWeatherScore,
        weatherSummary: result.summaryRow.weatherSummary
      }, null, 2));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      errors.push({
        instrument: symbol,
        bar: barConfig.bar,
        message
      });
      console.error(`[multi-weather] ${label} failed: ${message}`);
    }
  }

  const barSummary = await writeBarSummary({
    config: barConfig,
    symbols,
    rows,
    errors,
    skipDownload,
    summaryOnly,
    fromReports,
    startedAt: barStartedAt
  });
  barSummaries.push(barSummary);
  allRows.push(...rows);
  allErrors.push(...errors);

  console.log(JSON.stringify({
    step: "multi-symbol-weather-bar-summary",
    ...barSummary,
    errors
  }, null, 2));
}

const combinedSummary = await writeCombinedSummary({
  bars,
  symbols,
  rows: allRows,
  errors: allErrors,
  skipDownload,
  summaryOnly,
  fromReports,
  startedAt
});

console.log(JSON.stringify({
  step: "multi-symbol-weather-summary",
  ...combinedSummary,
  barSummaries,
  errors: allErrors
}, null, 2));

if (!allRows.length || allErrors.length) {
  process.exitCode = 1;
}
