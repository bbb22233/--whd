import { predictDecisionTree, trainDecisionTree } from "./decision-tree.mjs";
import { buildFeatureFactoryDataset } from "./feature-factory.mjs";
import { augmentDatasetWithMacro } from "./macro-data.mjs";
import { runStrategyRouterBacktest } from "./strategy-router-backtest.mjs";

const featureNames = {
  rangePct: "振幅率",
  atrPct: "ATR率",
  atrPercentile: "ATR百分位",
  volatilityMultiple: "振幅/ATR",
  volatilityMultiplePercentile: "振幅/ATR百分位",
  volatilityExcess: "波动超额",
  remainingMomentumPct: "剩余动能率",
  remainingMomentumAtr: "剩余动能ATR",
  atr3Pct: "3日ATR率",
  atr8Pct: "8日ATR率",
  atr13Pct: "13日ATR率",
  atr21Pct: "21日ATR率",
  atr3Percentile: "3日ATR百分位",
  atr8Percentile: "8日ATR百分位",
  atr13Percentile: "13日ATR百分位",
  atr21Percentile: "21日ATR百分位",
  volatilityMultiple3: "振幅/3日ATR",
  volatilityMultiple8: "振幅/8日ATR",
  volatilityMultiple13: "振幅/13日ATR",
  volatilityMultiple21: "振幅/21日ATR",
  volatilityMultiple3Percentile: "振幅/3日ATR百分位",
  volatilityMultiple8Percentile: "振幅/8日ATR百分位",
  volatilityMultiple13Percentile: "振幅/13日ATR百分位",
  volatilityMultiple21Percentile: "振幅/21日ATR百分位",
  atr3To21: "3/21日ATR比",
  atr8To21: "8/21日ATR比",
  atr13To21: "13/21日ATR比",
  atr3To8: "3/8日ATR比",
  atr8To13: "8/13日ATR比",
  volumeMultiple: "量能倍率",
  d8: "8日涨跌",
  d13: "13日涨跌",
  d21: "21日涨跌",
  d34: "34日涨跌",
  trendScore: "趋势动能",
  resonanceCount: "共振数量",
  middleDeviationRate: "中值乖离率",
  middleDeviationAtr: "中值乖离ATR",
  middlePositionPct: "中值位置百分位",
  maDeviationRate: "233MA乖离率",
  maDeviationAtr: "233MA乖离ATR",
  maPositionPct: "MA位置百分位",
  stretchHeat: "拉伸热度"
};

const strategyNames = {
  trendLong: "趋势追多",
  trendShort: "趋势做空",
  breakoutUp: "向上突破",
  breakoutDown: "向下突破",
  meanReversionLong: "低吸均值回归",
  meanReversionShort: "高抛均值回归",
  gridNeutral: "震荡网格",
  waitDefense: "防守等待"
};

const strategyClassNames = {
  fit: "适合",
  notFit: "不适合"
};

const volatilityClassNames = {
  volUp: "波动升高",
  volDown: "波动降低",
  volFlat: "波动平稳"
};

export const macroRegimes = [
  {
    key: "bear_repair_2018_2019",
    label: "2018熊末/2019修复",
    from: "2018-05-31",
    to: "2019-12-31"
  },
  {
    key: "liquidity_bull_2020_2021",
    label: "2020-2021宽松牛市",
    from: "2020-01-01",
    to: "2021-11-10"
  },
  {
    key: "tightening_bear_2021_2022",
    label: "2021-2022加息熊市",
    from: "2021-11-11",
    to: "2022-12-31"
  },
  {
    key: "repair_2023",
    label: "2023流动性修复",
    from: "2023-01-01",
    to: "2023-12-31"
  },
  {
    key: "etf_halving_2024",
    label: "2024 ETF/减半周期",
    from: "2024-01-01",
    to: "2024-12-31"
  },
  {
    key: "late_cycle_2025_2026",
    label: "2025-2026后周期/风险重估",
    from: "2025-01-01",
    to: "2026-12-31"
  }
];

function finite(value) {
  return Number.isFinite(value);
}

function safeDivide(numerator, denominator) {
  if (!finite(numerator) || !finite(denominator) || denominator === 0) return 0;
  return numerator / denominator;
}

function round(value, digits = 4) {
  if (!finite(value)) return 0;
  return Number(value.toFixed(digits));
}

function inWindow(date, config) {
  if (config.fromDate && date < config.fromDate) return false;
  if (config.toDate && date > config.toDate) return false;
  return true;
}

function inDateRange(date, from, to) {
  if (from && date < from) return false;
  if (to && date > to) return false;
  return true;
}

function readableFeatures(features) {
  return features.map((feature) => ({
    ...feature,
    label: featureNames[feature.key] || feature.label
  }));
}

function classifyVolatilityMove(currentSnapshot, futureSnapshot) {
  const changePct = safeDivide(
    futureSnapshot.volatility.atrPct - currentSnapshot.volatility.atrPct,
    currentSnapshot.volatility.atrPct
  ) * 100;

  if (changePct >= 5) return "volUp";
  if (changePct <= -5) return "volDown";
  return "volFlat";
}

function strategyFitLabel(row) {
  if (!row || row.success !== 1) return "notFit";
  if (row.routeKey === "gridNeutral" || row.routeKey === "waitDefense") return "fit";
  return row.routeReturnPct > 0 ? "fit" : "notFit";
}

function groupStrategyRows(observationRows) {
  const groups = new Map();

  for (const row of observationRows) {
    groups.set(`${row.date}::${row.horizon}::${row.routeKey}`, row);
  }

  return groups;
}

function classDistribution(rows, key = "actual") {
  const counts = new Map();
  for (const row of rows) {
    const value = row[key];
    counts.set(value, (counts.get(value) || 0) + 1);
  }

  return Array.from(counts.entries())
    .map(([label, count]) => ({
      label,
      count,
      sharePct: safeDivide(count, rows.length) * 100
    }))
    .sort((left, right) => right.count - left.count);
}

function distributionText(distribution, classNames = {}) {
  return distribution
    .slice(0, 4)
    .map((item) => `${classNames[item.label] || item.label}:${round(item.sharePct, 1)}%`)
    .join(" | ");
}

function predictionText(prediction, classNames = {}) {
  return classNames[prediction] || prediction || "";
}

function makeVolatilitySamples(rows, snapshotByIndex, horizon) {
  return rows.flatMap((row) => {
    const futureSnapshot = snapshotByIndex.get(row.snapshot.index + horizon);
    if (!futureSnapshot) return [];
    return [{
      date: row.date,
      values: row.values,
      label: classifyVolatilityMove(row.snapshot, futureSnapshot)
    }];
  });
}

function makeStrategySamples(rows, strategyGroups, horizon, routeKey) {
  return rows.flatMap((row) => {
    const strategyRow = strategyGroups.get(`${row.date}::${horizon}::${routeKey}`);
    if (!strategyRow) return [];
    return [{
      date: row.date,
      values: row.values,
      label: strategyFitLabel(strategyRow)
    }];
  });
}

function evaluateTree(tree, validationSamples, meta) {
  return validationSamples.map((sample) => {
    const prediction = predictDecisionTree(tree, sample.values);
    return {
      ...meta,
      date: sample.date,
      actual: sample.label,
      actualLabel: predictionText(sample.label, meta.classNames),
      prediction: prediction.prediction,
      predictionLabel: predictionText(prediction.prediction, meta.classNames),
      correct: prediction.prediction === sample.label ? 1 : 0
    };
  });
}

function validationQuality(row) {
  const reasons = [];

  if (row.validationSamples < 100) reasons.push("验证样本少于100");

  if (row.treeType === "策略适配树") {
    const fitGood = row.fitSignalCount >= 50 && row.fitPrecisionPct >= 55 && row.fitLiftPct >= 5;
    const notFitGood = row.notFitSignalCount >= 50 && row.notFitPrecisionPct >= 55 && row.notFitLiftPct >= 5;

    if (!fitGood && !notFitGood) {
      if (row.fitSignalCount < 50 && row.notFitSignalCount < 50) reasons.push("有效信号样本不足");
      if (Math.max(row.fitLiftPct, row.notFitLiftPct) < 5) reasons.push("相对基准提升不足5%");
      if (Math.max(row.fitPrecisionPct, row.notFitPrecisionPct) < 55) reasons.push("验证精度不足55%");
      if (!reasons.length) reasons.push("没有通过适合/不适合信号完整门槛");
    }

    if (reasons.length) return { validationQuality: "弱参考", validationReason: reasons.join("；") };
    if (row.validationSamples >= 200 && (row.fitLiftPct >= 8 || row.notFitLiftPct >= 8)) {
      return { validationQuality: "强参考", validationReason: "时间外验证存在稳定提升" };
    }
    return { validationQuality: "观察", validationReason: "时间外验证有提升，但还不够强" };
  }

  if (row.accuracyPct < 50) reasons.push("准确率低于50%");
  if (row.accuracyLiftPct < 5) reasons.push("相对多数类基准提升不足5%");

  if (reasons.length) return { validationQuality: "弱参考", validationReason: reasons.join("；") };
  if (row.validationSamples >= 200 && row.accuracyPct >= 60 && row.accuracyLiftPct >= 5) {
    return { validationQuality: "强参考", validationReason: "时间外准确率和基准提升达标" };
  }
  return { validationQuality: "观察", validationReason: "时间外验证有提升，但还不够强" };
}

function summarizePredictions(predictions) {
  if (!predictions.length) return null;

  const first = predictions[0];
  const actualDistribution = classDistribution(predictions, "actual");
  const predictedDistribution = classDistribution(predictions, "prediction");
  const accuracyPct = safeDivide(
    predictions.filter((row) => row.correct === 1).length,
    predictions.length
  ) * 100;
  const baselineAccuracyPct = actualDistribution[0]?.sharePct || 0;
  const fitSignalRows = predictions.filter((row) => row.prediction === "fit");
  const notFitSignalRows = predictions.filter((row) => row.prediction === "notFit");
  const baselineFitPct = safeDivide(predictions.filter((row) => row.actual === "fit").length, predictions.length) * 100;
  const baselineNotFitPct = 100 - baselineFitPct;
  const fitPrecisionPct = safeDivide(fitSignalRows.filter((row) => row.actual === "fit").length, fitSignalRows.length) * 100;
  const notFitPrecisionPct = safeDivide(notFitSignalRows.filter((row) => row.actual === "notFit").length, notFitSignalRows.length) * 100;

  const row = {
    scope: first.scope,
    regimeKey: first.regimeKey || "",
    regimeLabel: first.regimeLabel || "",
    trainFrom: first.trainFrom,
    trainTo: first.trainTo,
    validateFrom: first.validateFrom,
    validateTo: first.validateTo,
    treeType: first.treeType,
    horizon: first.horizon,
    routeKey: first.routeKey || "",
    routeLabel: first.routeLabel || "",
    trainSamples: first.trainSamples,
    validationSamples: predictions.length,
    accuracyPct: round(accuracyPct, 2),
    baselineAccuracyPct: round(baselineAccuracyPct, 2),
    accuracyLiftPct: round(accuracyPct - baselineAccuracyPct, 2),
    actualDistribution: distributionText(actualDistribution, first.classNames),
    predictedDistribution: distributionText(predictedDistribution, first.classNames),
    fitSignalCount: fitSignalRows.length,
    fitPrecisionPct: round(fitPrecisionPct, 2),
    baselineFitPct: round(baselineFitPct, 2),
    fitLiftPct: round(fitPrecisionPct - baselineFitPct, 2),
    notFitSignalCount: notFitSignalRows.length,
    notFitPrecisionPct: round(notFitPrecisionPct, 2),
    baselineNotFitPct: round(baselineNotFitPct, 2),
    notFitLiftPct: round(notFitPrecisionPct - baselineNotFitPct, 2)
  };

  return {
    ...row,
    ...validationQuality(row)
  };
}

function evaluateSplit({
  scope,
  regimeKey = "",
  regimeLabel = "",
  trainRows,
  validationRows,
  trainFrom,
  trainTo,
  validateFrom,
  validateTo,
  features,
  snapshotByIndex,
  strategyGroups,
  config
}) {
  const summaryRows = [];
  const predictionRows = [];

  for (const horizon of config.horizons) {
    const trainSamples = makeVolatilitySamples(trainRows, snapshotByIndex, horizon);
    const validationSamples = makeVolatilitySamples(validationRows, snapshotByIndex, horizon);
    if (trainSamples.length >= 200 && validationSamples.length >= 30) {
      const tree = trainDecisionTree(trainSamples, features, {
        ...config.decisionTree,
        classNames: volatilityClassNames
      });
      const predictions = evaluateTree(tree, validationSamples, {
        scope,
        regimeKey,
        regimeLabel,
        trainFrom,
        trainTo,
        validateFrom,
        validateTo,
        treeType: "波动变化树",
        horizon,
        routeKey: "",
        routeLabel: "",
        trainSamples: trainSamples.length,
        classNames: volatilityClassNames
      });
      const summary = summarizePredictions(predictions);
      if (summary) summaryRows.push(summary);
      predictionRows.push(...predictions);
    }

    for (const routeKey of Object.keys(strategyNames)) {
      const routeLabel = strategyNames[routeKey];
      const strategyTrainSamples = makeStrategySamples(trainRows, strategyGroups, horizon, routeKey);
      const strategyValidationSamples = makeStrategySamples(validationRows, strategyGroups, horizon, routeKey);
      if (strategyTrainSamples.length < 200 || strategyValidationSamples.length < 30) continue;

      const tree = trainDecisionTree(strategyTrainSamples, features, {
        ...config.decisionTree,
        classNames: strategyClassNames
      });
      const predictions = evaluateTree(tree, strategyValidationSamples, {
        scope,
        regimeKey,
        regimeLabel,
        trainFrom,
        trainTo,
        validateFrom,
        validateTo,
        treeType: "策略适配树",
        horizon,
        routeKey,
        routeLabel,
        trainSamples: strategyTrainSamples.length,
        classNames: strategyClassNames
      });
      const summary = summarizePredictions(predictions);
      if (summary) summaryRows.push(summary);
      predictionRows.push(...predictions);
    }
  }

  return {
    summaryRows,
    predictionRows
  };
}

export function validateDecisionTrees(cleanPayload, config, options = {}) {
  const trainTo = options.trainTo || "2023-12-31";
  const validateFrom = options.validateFrom || "2024-01-01";
  const validateTo = options.validateTo || config.toDate || cleanPayload.metadata.lastDate || "9999-12-31";
  const { snapshots, dataset: baseDataset } = buildFeatureFactoryDataset(cleanPayload, config);
  const dataset = augmentDatasetWithMacro(baseDataset, options.macroRows || []);
  const selectedRows = dataset.rows.filter((row) => inWindow(row.date, config));
  const features = readableFeatures(dataset.features);
  const snapshotByIndex = new Map(snapshots.map((snapshot) => [snapshot.index, snapshot]));
  const routerBacktest = runStrategyRouterBacktest(cleanPayload, config);
  const strategyGroups = groupStrategyRows(routerBacktest.observationRows);
  const trainRows = selectedRows.filter((row) => row.date <= trainTo);
  const validationRows = selectedRows.filter((row) => row.date >= validateFrom && row.date <= validateTo);
  const holdout = evaluateSplit({
    scope: "holdout",
    trainRows,
    validationRows,
    trainFrom: trainRows[0]?.date || "",
    trainTo,
    validateFrom,
    validateTo,
    features,
    snapshotByIndex,
    strategyGroups,
    config
  });

  const regimeRows = [];
  const regimePredictionRows = [];
  for (const regime of macroRegimes) {
    const regimeTrainRows = selectedRows.filter((row) => row.date < regime.from);
    const regimeValidationRows = selectedRows.filter((row) => inDateRange(row.date, regime.from, regime.to));
    if (regimeTrainRows.length < 300 || regimeValidationRows.length < 60) continue;

    const result = evaluateSplit({
      scope: "macro-regime",
      regimeKey: regime.key,
      regimeLabel: regime.label,
      trainRows: regimeTrainRows,
      validationRows: regimeValidationRows,
      trainFrom: regimeTrainRows[0]?.date || "",
      trainTo: regimeTrainRows.at(-1)?.date || "",
      validateFrom: regime.from,
      validateTo: regime.to,
      features,
      snapshotByIndex,
      strategyGroups,
      config
    });
    regimeRows.push(...result.summaryRows);
    regimePredictionRows.push(...result.predictionRows);
  }

  return {
    metadata: {
      instrument: cleanPayload.metadata.instrument,
      bar: cleanPayload.metadata.bar,
      firstDate: selectedRows[0]?.date || null,
      lastDate: selectedRows.at(-1)?.date || null,
      trainTo,
      validateFrom,
      validateTo,
      horizons: config.horizons,
      generatedAt: new Date().toISOString(),
      macroEnabled: dataset.macroEnabled,
      macroRegimes,
      note: "宏观周期为人工日期分段代理，不等同于已接入外部宏观数据"
    },
    holdoutRows: holdout.summaryRows,
    regimeRows,
    predictionRows: [
      ...holdout.predictionRows,
      ...regimePredictionRows
    ]
  };
}
