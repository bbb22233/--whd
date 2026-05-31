import {
  decisionTreeImportanceRows,
  predictDecisionTree,
  trainDecisionTree
} from "./decision-tree.mjs";
import { buildFeatureFactoryDataset } from "./feature-factory.mjs";
import { augmentDatasetWithMacro } from "./macro-data.mjs";
import { trainMarketStateModel } from "./market-state.mjs";
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
  remainingMomentumAtr3: "3日剩余动能ATR",
  remainingMomentumAtr8: "8日剩余动能ATR",
  remainingMomentumAtr13: "13日剩余动能ATR",
  remainingMomentumAtr21: "21日剩余动能ATR",
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

function readableFeatures(features) {
  return features.map((feature) => ({
    ...feature,
    label: featureNames[feature.key] || feature.label
  }));
}

function formatPath(path) {
  if (!path.length) return "ALL";
  return path.map((item) => {
    const label = featureNames[item.featureKey] || item.featureLabel;
    return `${label} ${item.operator} ${round(item.threshold)} (当前 ${round(item.value)})`;
  }).join(" AND ");
}

function formatRulePath(path) {
  if (!path.length) return "ALL";
  return path.map((item) => {
    const label = featureNames[item.featureKey] || item.featureLabel;
    return `${label} ${item.operator} ${round(item.threshold)}`;
  }).join(" AND ");
}

function distributionText(distribution) {
  return distribution
    .slice(0, 4)
    .map((item) => `${item.name}:${round(item.sharePct, 1)}%`)
    .join(" | ");
}

function distributionStats(distribution) {
  const top = distribution[0] || { name: "", sharePct: 0, count: 0 };
  const second = distribution[1] || { name: "", sharePct: 0, count: 0 };

  return {
    topClass: top.name,
    topSharePct: round(top.sharePct, 2),
    secondClass: second.name,
    secondSharePct: round(second.sharePct, 2),
    edgePct: round(top.sharePct - second.sharePct, 2)
  };
}

function baselineShare(distribution, label) {
  if (!label) return "";
  const item = distribution.find((row) => row.label === label);
  return item ? round(item.sharePct, 2) : 0;
}

function binaryShare(distribution, label) {
  const item = distribution.find((row) => row.label === label);
  return item ? round(item.sharePct, 2) : "";
}

function auditQuality(samples, purityPct, edgePct, liftPct) {
  const reasons = [];

  if (samples < 200) reasons.push("样本少于200");
  if (purityPct < 50) reasons.push("纯度低于50%");
  if (edgePct < 10) reasons.push("第一名领先不足10%");
  if (liftPct !== "" && liftPct < 5) reasons.push("相对基准提升不足5%");

  if (reasons.length) {
    return {
      quality: "弱参考",
      auditReason: reasons.join("；")
    };
  }

  if (samples >= 300 && purityPct >= 65 && edgePct >= 20 && (liftPct === "" || liftPct >= 5)) {
    return {
      quality: "强参考",
      auditReason: "样本、纯度、优势差距都达标"
    };
  }

  return {
    quality: "观察",
    auditReason: "达最低门槛，但还不够强"
  };
}

function attachAudit(row, distribution, baselineDistribution = []) {
  const stats = distributionStats(distribution);
  const baselinePct = baselineShare(baselineDistribution, row.predictionKey);
  const liftPct = baselinePct === "" ? "" : round(stats.topSharePct - baselinePct, 2);
  const quality = auditQuality(row.samples, row.purityPct, stats.edgePct, liftPct);

  return {
    ...row,
    ...stats,
    baselinePct,
    liftPct,
    fitProbabilityPct: binaryShare(distribution, "fit"),
    notFitProbabilityPct: binaryShare(distribution, "notFit"),
    ...quality
  };
}

function readablePrediction(prediction) {
  return {
    ...prediction,
    path: prediction.path.map((item) => ({
      ...item,
      featureLabel: featureNames[item.featureKey] || item.featureLabel,
      rawFeatureLabel: item.featureLabel,
      threshold: round(item.threshold),
      value: round(item.value)
    })),
    conditionText: formatPath(prediction.path)
  };
}

function normalizeRuleRows(treeResult, treeType, horizon = "", meta = {}) {
  const baselineDistribution = treeResult.tree?.distribution || [];

  return treeResult.rules.map((rule) => attachAudit({
    treeType,
    horizon,
    routeKey: meta.routeKey || "",
    routeLabel: meta.routeLabel || "",
    ruleId: rule.id,
    predictionKey: rule.prediction,
    prediction: rule.predictionName,
    samples: rule.samples,
    purityPct: rule.purityPct,
    conditions: formatRulePath(rule.path),
    distribution: distributionText(rule.distribution)
  }, rule.distribution, baselineDistribution));
}

function normalizeImportanceRows(rows, treeType, horizon = "") {
  return rows.map((row) => ({
    treeType,
    horizon,
    rank: row.rank,
    feature: featureNames[row.featureKey] || row.feature,
    featureKey: row.featureKey,
    importance: row.importance
  }));
}

function stateCurrentRow(stateModel, currentValues) {
  const current = stateModel.currentState;
  if (!current) return null;
  const prediction = readablePrediction(predictDecisionTree(stateModel.decisionTree, currentValues));

  return attachAudit({
    treeType: "状态解释树",
    horizon: "",
    routeKey: "",
    routeLabel: "",
    predictionKey: prediction.prediction,
    prediction: prediction.predictionName,
    samples: prediction.samples,
    purityPct: prediction.purityPct,
    conditionText: prediction.conditionText,
    distribution: distributionText(prediction.distribution),
    note: "解释神经网络为什么把当前行情归到这个市场状态"
  }, prediction.distribution, stateModel.decisionTree.tree?.distribution || []);
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

function trainVolatilityTrees(datasetRows, snapshotByIndex, features, config) {
  const trees = [];

  for (const horizon of config.horizons) {
    const samples = datasetRows.flatMap((row) => {
      if (!inWindow(row.date, config)) return [];
      const futureSnapshot = snapshotByIndex.get(row.snapshot.index + horizon);
      if (!futureSnapshot) return [];
      return [{
        values: row.values,
        label: classifyVolatilityMove(row.snapshot, futureSnapshot)
      }];
    });

    const tree = trainDecisionTree(samples, features, {
      ...config.decisionTree,
      classNames: volatilityClassNames
    });
    trees.push({
      horizon,
      tree,
      samples: samples.length
    });
  }

  return trees;
}

function strategyFitLabel(row) {
  if (!row || row.success !== 1) return "notFit";
  if (row.routeKey === "gridNeutral" || row.routeKey === "waitDefense") return "fit";
  return row.routeReturnPct > 0 ? "fit" : "notFit";
}

function groupStrategyRows(observationRows) {
  const groups = new Map();

  for (const row of observationRows) {
    const key = `${row.date}::${row.horizon}::${row.routeKey}`;
    groups.set(key, row);
  }

  return groups;
}

function trainStrategyTrees(datasetRows, features, cleanPayload, config) {
  const routerBacktest = runStrategyRouterBacktest(cleanPayload, config);
  const strategyGroups = groupStrategyRows(routerBacktest.observationRows);
  const trees = [];

  for (const horizon of config.horizons) {
    for (const routeKey of Object.keys(strategyNames)) {
      const samples = datasetRows.flatMap((row) => {
        if (!inWindow(row.date, config)) return [];
        const strategyRow = strategyGroups.get(`${row.date}::${horizon}::${routeKey}`);
        if (!strategyRow) return [];
        return [{
          values: row.values,
          label: strategyFitLabel(strategyRow)
        }];
      });

      const tree = trainDecisionTree(samples, features, {
        ...config.decisionTree,
        classNames: strategyClassNames
      });
      trees.push({
        horizon,
        routeKey,
        routeLabel: strategyNames[routeKey],
        tree,
        samples: samples.length
      });
    }
  }

  return trees;
}

function predictionRow(treeType, horizon, prediction, note, meta = {}) {
  return attachAudit({
    treeType,
    horizon,
    routeKey: meta.routeKey || "",
    routeLabel: meta.routeLabel || "",
    predictionKey: prediction.prediction,
    prediction: prediction.predictionName,
    samples: prediction.samples,
    purityPct: prediction.purityPct,
    conditionText: prediction.conditionText,
    distribution: distributionText(prediction.distribution),
    note
  }, prediction.distribution, meta.baselineDistribution || []);
}

export function trainDecisionTreeSuite(cleanPayload, config, options = {}) {
  const stateModel = trainMarketStateModel(cleanPayload, config);
  const { snapshots, dataset: baseDataset } = buildFeatureFactoryDataset(cleanPayload, config);
  const dataset = augmentDatasetWithMacro(baseDataset, options.macroRows || []);
  const features = readableFeatures(dataset.features);
  const selectedRows = dataset.rows.filter((row) => inWindow(row.date, config));
  const snapshotByIndex = new Map(snapshots.map((snapshot) => [snapshot.index, snapshot]));
  const currentRow = selectedRows.at(-1);
  const volatilityTrees = trainVolatilityTrees(selectedRows, snapshotByIndex, features, config);
  const strategyTrees = trainStrategyTrees(selectedRows, features, cleanPayload, config);
  const currentRows = [];
  const stateRow = stateCurrentRow(stateModel, currentRow.values);

  if (stateRow) currentRows.push(stateRow);

  for (const item of volatilityTrees) {
    const prediction = readablePrediction(predictDecisionTree(item.tree, currentRow.values));
    currentRows.push(predictionRow(
      "波动变化树",
      item.horizon,
      prediction,
      "判断未来该周期 ATR 更容易升高、降低，还是保持平稳",
      {
        baselineDistribution: item.tree.tree?.distribution || []
      }
    ));
  }

  for (const item of strategyTrees) {
    const prediction = readablePrediction(predictDecisionTree(item.tree, currentRow.values));
    currentRows.push(predictionRow(
      "策略适配树",
      item.horizon,
      prediction,
      "单独判断这个策略在类似天气下适合还是不适合",
      {
        routeKey: item.routeKey,
        routeLabel: item.routeLabel,
        baselineDistribution: item.tree.tree?.distribution || []
      }
    ));
  }

  const ruleRows = [
    ...normalizeRuleRows(stateModel.decisionTree, "状态解释树"),
    ...volatilityTrees.flatMap((item) => normalizeRuleRows(item.tree, "波动变化树", item.horizon)),
    ...strategyTrees.flatMap((item) => normalizeRuleRows(item.tree, "策略适配树", item.horizon, {
      routeKey: item.routeKey,
      routeLabel: item.routeLabel
    }))
  ];
  const importanceRows = [
    ...normalizeImportanceRows(decisionTreeImportanceRows(stateModel.decisionTree), "状态解释树"),
    ...volatilityTrees.flatMap((item) => normalizeImportanceRows(decisionTreeImportanceRows(item.tree), "波动变化树", item.horizon)),
    ...strategyTrees.flatMap((item) => normalizeImportanceRows(decisionTreeImportanceRows(item.tree), "策略适配树", item.horizon))
  ];

  return {
    metadata: {
      instrument: cleanPayload.metadata.instrument,
      bar: cleanPayload.metadata.bar,
      firstDate: selectedRows[0]?.date || null,
      lastDate: currentRow?.date || null,
      snapshotCount: selectedRows.length,
      horizons: config.horizons,
      generatedAt: new Date().toISOString(),
      macroEnabled: dataset.macroEnabled,
      volatilityTarget: "未来 N 日 ATR率变化 >= 5% 为波动升高，<= -5% 为波动降低，其余为波动平稳",
      strategyTarget: "每个策略单独二分类：未来 N 日该策略成功且收益口径达标为适合，否则为不适合",
      qualityAudit: "弱参考=样本<200或纯度<50%或领先<10%或相对基准提升<5%；强参考=样本>=300、纯度>=65%、领先>=20%、相对基准提升>=5%"
    },
    current: {
      date: currentRow.date,
      close: round(currentRow.close, 2),
      rows: currentRows
    },
    stateTree: {
      currentState: stateModel.currentState,
      tree: stateModel.decisionTree
    },
    volatilityTrees,
    strategyTrees,
    currentRows,
    ruleRows,
    qualityRows: ruleRows,
    importanceRows
  };
}
