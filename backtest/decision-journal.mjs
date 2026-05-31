import { buildFeatureFactory } from "./feature-factory.mjs";
import { trainMarketStateModel } from "./market-state.mjs";
import { runRouterCalibration } from "./router-calibrator.mjs";

const routeNames = {
  trendLong: "趋势追多",
  trendShort: "趋势做空",
  breakoutUp: "向上突破",
  breakoutDown: "向下突破",
  meanReversionLong: "低吸均值回归",
  meanReversionShort: "高抛均值回归",
  gridNeutral: "震荡网格",
  waitDefense: "防守等待"
};

const signalTypeNames = {
  "鏂瑰悜淇″彿": "方向信号",
  "娉㈠姩鏂瑰悜淇″彿": "波动方向信号",
  "浣嶇疆鍥炲綊淇″彿": "位置回归信号",
  "闇囪崱鐘舵€佷俊鍙?": "震荡状态信号",
  "椋庨櫓杩囨护淇″彿": "风险过滤信号",
  "鐘舵€佷俊鍙?": "状态信号"
};

const lightNames = {
  "缁跨伅": "绿灯",
  "榛勭伅": "黄灯",
  "绾㈢伅": "红灯",
  "瑙傚療": "观察",
  "鏍锋湰灏?": "样本少"
};

const featureNames = {
  rangePct: "振幅率",
  atrPct: "ATR率",
  atrPercentile: "ATR百分位",
  volatilityMultiple: "振幅/ATR",
  volatilityMultiplePercentile: "振幅/ATR百分位",
  volatilityExcess: "波动超额",
  remainingMomentumPct: "波动超额率",
  remainingMomentumAtr: "波动超额ATR",
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
  remainingMomentumAtr3: "3日波动超额ATR",
  remainingMomentumAtr8: "8日波动超额ATR",
  remainingMomentumAtr13: "13日波动超额ATR",
  remainingMomentumAtr21: "21日波动超额ATR",
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

const keyMetricDefs = [
  "rangePct",
  "atrPct",
  "atrPercentile",
  "volatilityMultiple",
  "volatilityMultiplePercentile",
  "remainingMomentumPct",
  "remainingMomentumAtr",
  "atr3Pct",
  "atr8Pct",
  "atr13Pct",
  "atr21Pct",
  "atr3Percentile",
  "atr8Percentile",
  "atr13Percentile",
  "atr21Percentile",
  "volatilityMultiple3",
  "volatilityMultiple8",
  "volatilityMultiple13",
  "volatilityMultiple21",
  "volatilityMultiple3Percentile",
  "volatilityMultiple8Percentile",
  "volatilityMultiple13Percentile",
  "volatilityMultiple21Percentile",
  "remainingMomentumAtr3",
  "remainingMomentumAtr8",
  "remainingMomentumAtr13",
  "remainingMomentumAtr21",
  "atr3To21",
  "atr8To21",
  "atr13To21",
  "volumeMultiple",
  "d8",
  "d13",
  "d21",
  "d34",
  "trendScore",
  "resonanceCount",
  "middleDeviationRate",
  "middleDeviationAtr",
  "middlePositionPct",
  "maDeviationRate",
  "maDeviationAtr",
  "maPositionPct",
  "stretchHeat"
];

function finite(value) {
  return Number.isFinite(value);
}

function clamp(value, min, max) {
  if (!finite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function round(value, digits = 4) {
  if (!finite(value)) return 0;
  return Number(value.toFixed(digits));
}

function safeId(value) {
  return String(value).replace(/[^a-zA-Z0-9_-]+/g, "_");
}

function readableLight(value) {
  if (!value) return "";
  if (lightNames[value]) return lightNames[value];
  if (String(value).startsWith("鏍锋")) return "样本少";
  return value;
}

function readableSignalType(value) {
  return signalTypeNames[value] || value || "";
}

function readableFeature(feature) {
  return {
    ...feature,
    label: featureNames[feature.key] || feature.label || feature.key,
    rawLabel: feature.label
  };
}

function normalizeRoute(route) {
  if (!route) return null;
  return {
    ...route,
    routeLabel: routeNames[route.routeKey || route.key] || route.routeLabel || route.label || "",
    rawRouteLabel: route.routeLabel || route.label || "",
    light: readableLight(route.light),
    rawLight: route.light,
    signalType: readableSignalType(route.signalType),
    rawSignalType: route.signalType
  };
}

function keyMetrics(values) {
  return keyMetricDefs
    .filter((key) => values && values[key] !== undefined)
    .map((key) => ({
      key,
      label: featureNames[key] || key,
      value: round(values[key])
    }));
}

function findDecisionRule(stateModel) {
  const currentState = stateModel.currentState;
  if (!currentState) return null;

  const rules = stateModel.decisionTree?.rules || [];
  const stateRules = rules.filter((rule) => Number(rule.prediction) === Number(currentState.id));
  const rule = stateRules.sort((left, right) =>
    right.purityPct - left.purityPct ||
    right.samples - left.samples
  )[0];
  if (!rule) return null;

  return {
    id: rule.id,
    prediction: rule.predictionName,
    samples: rule.samples,
    purityPct: rule.purityPct,
    conditions: rule.path.map((condition) => ({
      ...condition,
      featureLabel: featureNames[condition.featureKey] || condition.featureLabel,
      rawFeatureLabel: condition.featureLabel,
      threshold: round(condition.threshold)
    })),
    conditionText: rule.path.length
      ? rule.path.map((condition) =>
          `${featureNames[condition.featureKey] || condition.featureLabel} ${condition.operator} ${round(condition.threshold)}`
        ).join(" AND ")
      : "ALL",
    distribution: rule.distributionText
  };
}

function compactHumanInput(input = {}) {
  return {
    decision: input.decision || "观察",
    bias: input.bias || "中性",
    confidence: clamp(Number(input.confidence ?? 50), 0, 100),
    notes: input.notes || "",
    tags: Array.isArray(input.tags) ? input.tags.filter(Boolean) : []
  };
}

export function buildDecisionJournal(cleanPayload, config, humanInput = {}) {
  const featureFactory = buildFeatureFactory(cleanPayload, config);
  const calibration = runRouterCalibration(cleanPayload, config);
  const stateModel = trainMarketStateModel(cleanPayload, config);
  const current = featureFactory.current;

  if (!current) {
    throw new Error("没有可写入决策日志的当前行情快照");
  }

  const currentState = stateModel.currentState;
  const createdAt = new Date().toISOString();
  const journal = {
    id: safeId(`${current.date}_${cleanPayload.metadata.instrument}_${cleanPayload.metadata.bar}`),
    createdAt,
    metadata: {
      instrument: cleanPayload.metadata.instrument,
      bar: cleanPayload.metadata.bar,
      firstDate: featureFactory.metadata.firstDate,
      lastDate: featureFactory.metadata.lastDate,
      snapshotCount: featureFactory.metadata.snapshotCount,
      horizons: config.horizons
    },
    market: {
      instrument: cleanPayload.metadata.instrument,
      bar: cleanPayload.metadata.bar,
      date: current.date,
      close: current.close
    },
    weather: {
      name: current.weatherName,
      confidencePct: current.weatherConfidencePct,
      labels: current.labels,
      keyMetrics: keyMetrics(current.values)
    },
    neuralState: currentState ? {
      stateId: currentState.id,
      stateCode: `S${currentState.id}`,
      name: currentState.name,
      confidence: currentState.confidence,
      distance: currentState.distance,
      topFeatures: currentState.topFeatures.map(readableFeature),
      weatherProfile: currentState.weatherProfile.slice(0, 8),
      strategyProfile: currentState.strategyProfile.slice(0, 8).map(normalizeRoute),
      decisionRule: findDecisionRule(stateModel)
    } : null,
    router: {
      topRoutes: current.topRoutes.map(normalizeRoute),
      currentSignals: (calibration.metadata.currentSignals || []).map(normalizeRoute)
    },
    human: compactHumanInput(humanInput),
    review: {
      status: "pending",
      horizons: config.horizons,
      outcomeFields: [
        "futureReturnPct",
        "futureAbsReturnPct",
        "futureRangePct",
        "atrChangePct",
        "stateChanged",
        "humanDecisionUseful"
      ],
      outcomes: []
    }
  };

  return {
    journal,
    sources: {
      featureFactory,
      calibration: {
        metadata: calibration.metadata,
        calibrationRows: calibration.calibrationRows
      },
      stateModel: {
        metadata: stateModel.metadata,
        currentState: stateModel.currentState,
        decisionImportanceRows: stateModel.decisionImportanceRows
      }
    }
  };
}

export function decisionJournalIndexRow(journal) {
  const bestRoute = journal.router.topRoutes[0] || {};
  const bestSignal = journal.router.currentSignals[0] || {};
  const greenOrYellow = journal.router.currentSignals
    .filter((signal) => signal.light === "绿灯" || signal.light === "黄灯")
    .map((signal) => `${signal.routeLabel}:${signal.light}`)
    .join(" | ");

  return {
    id: journal.id,
    createdAt: journal.createdAt,
    instrument: journal.market.instrument,
    bar: journal.market.bar,
    date: journal.market.date,
    close: journal.market.close,
    humanDecision: journal.human.decision,
    humanBias: journal.human.bias,
    humanConfidence: journal.human.confidence,
    humanTags: journal.human.tags.join(" | "),
    humanNotes: journal.human.notes,
    weatherName: journal.weather.name,
    weatherConfidencePct: journal.weather.confidencePct,
    stateCode: journal.neuralState?.stateCode || "",
    stateName: journal.neuralState?.name || "",
    stateConfidence: journal.neuralState?.confidence || "",
    bestRoute: bestRoute.routeLabel || "",
    bestRouteScore: bestRoute.score || "",
    bestSignal: bestSignal.routeLabel || "",
    bestSignalLight: bestSignal.light || "",
    bestSignalScore: bestSignal.currentScore || "",
    greenOrYellowSignals: greenOrYellow
  };
}
