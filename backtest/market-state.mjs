import { buildFeatureFactoryDataset, buildWeatherLabels } from "./feature-factory.mjs";
import { decisionTreeImportanceRows, decisionTreeRuleRows, trainDecisionTree } from "./decision-tree.mjs";
import { runStrategyRouterBacktest } from "./strategy-router-backtest.mjs";
import { meanFeatureValues, strongestFeatures, zProfile } from "./state-features.mjs";
import { assignSom, trainSom } from "./som.mjs";

const DEFAULT_PROFILE_TRAIN_TO = "2023-12-31";
const DEFAULT_PROFILE_VALIDATE_FROM = "2024-01-01";
const MIN_ROUTE_LIGHT_OCCURRENCES = 25;

function safeDivide(numerator, denominator) {
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator === 0) return 0;
  return numerator / denominator;
}

function average(values) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function round(value, digits = 4) {
  if (!Number.isFinite(value)) return 0;
  return Number(value.toFixed(digits));
}

function dateKey(value) {
  return String(value || "").slice(0, 10);
}

function inDateRange(date, from, to) {
  const day = dateKey(date);
  if (from && day < dateKey(from)) return false;
  if (to && day > dateKey(to)) return false;
  return true;
}

function routeSignalType(routeKey) {
  if (routeKey.startsWith("trend")) return "方向信号";
  if (routeKey.startsWith("breakout")) return "波动方向信号";
  if (routeKey.startsWith("meanReversion")) return "位置回归信号";
  if (routeKey === "gridNeutral") return "震荡状态信号";
  if (routeKey === "waitDefense") return "风险过滤信号";
  return "状态信号";
}

function positionSide(profile) {
  const combined = profile.middleDeviationAtr + profile.maDeviationAtr;
  if (combined > 0.75) return "上侧";
  if (combined < -0.75) return "下侧";
  return "";
}

function nameState(profile) {
  const side = positionSide(profile);
  const absTrend = Math.abs(profile.trendScore);
  const highVol = profile.volatilityMultiple >= 1.2;
  const lowVol = profile.volatilityMultiple <= 0.82;
  const highVolume = profile.volumeMultiple >= 1.35;
  const lowVolume = profile.volumeMultiple <= 0.82;
  const stretched = profile.stretchHeat >= 68;
  const compact = profile.stretchHeat <= 34;
  const resonant = profile.resonanceCount >= 3 && absTrend >= 3;

  if (highVol && highVolume && stretched) return `${side}放量扩张拉伸态`.trim();
  if (highVol && highVolume) return "放量波动扩张态";
  if (stretched && resonant) return `${side || "中性"}趋势拉伸共振态`;
  if (stretched) return `${side || "中性"}极端拉伸态`;
  if (resonant) return `${side || "中性"}趋势共振态`;
  if (highVol) return "波动扩张态";
  if (highVolume) return "放量换手态";
  if (lowVol && lowVolume && compact) return "低波动压缩态";
  if (compact && absTrend < 1.4) return "中性震荡态";
  return "过渡混合态";
}

function confidence(bestDistance, secondDistance) {
  if (!Number.isFinite(bestDistance) || !Number.isFinite(secondDistance) || secondDistance === 0) return 0;
  return Math.max(0, Math.min(1, 1 - (bestDistance / secondDistance)));
}

function typicalRows(rows, limit = 5) {
  return [...rows]
    .sort((left, right) => left.assignment.distance - right.assignment.distance)
    .slice(0, limit)
    .map((row) => ({
      date: row.date,
      close: round(row.close, 2),
      distance: round(row.assignment.distance, 4)
    }));
}

function weatherProfile(rows, config) {
  const counts = new Map();

  for (const row of rows) {
    for (const label of buildWeatherLabels(row.snapshot, config)) {
      const key = `${label.dimension}::${label.label}`;
      const item = counts.get(key) || {
        dimension: label.dimension,
        label: label.label,
        count: 0,
        confidenceSum: 0
      };
      item.count += 1;
      item.confidenceSum += label.confidence;
      counts.set(key, item);
    }
  }

  return Array.from(counts.values())
    .map((item) => ({
      dimension: item.dimension,
      label: item.label,
      sharePct: safeDivide(item.count, rows.length) * 100,
      avgConfidencePct: safeDivide(item.confidenceSum, item.count) * 100
    }))
    .sort((left, right) =>
      left.dimension.localeCompare(right.dimension, "zh-CN") ||
      right.sharePct - left.sharePct
    );
}

function summarizeRouteGroup(groupRows) {
  const first = groupRows[0];
  const directionalRows = groupRows.filter((row) => row.directionalWin !== "");
  const directionalWinRatePct = directionalRows.length
    ? safeDivide(directionalRows.filter((row) => row.directionalWin === 1).length, directionalRows.length) * 100
    : null;
  const successRatePct = safeDivide(groupRows.filter((row) => row.success === 1).length, groupRows.length) * 100;
  const avgRouteReturnPct = average(groupRows.map((row) => row.routeReturnPct));
  const avgScore = average(groupRows.map((row) => row.score));

  return {
    routeKey: first.routeKey,
    routeLabel: first.routeLabel,
    family: first.family,
    direction: first.direction,
    signalType: routeSignalType(first.routeKey),
    horizon: first.horizon,
    occurrences: groupRows.length,
    avgScore,
    successRatePct,
    directionalWinRatePct,
    avgRouteReturnPct,
    avgFutureReturnPct: average(groupRows.map((row) => row.futureReturnPct)),
    avgAbsReturnPct: average(groupRows.map((row) => row.absReturnPct))
  };
}

function routeLight(profile) {
  if (profile.occurrences < MIN_ROUTE_LIGHT_OCCURRENCES) return "样本少";

  if (profile.signalType === "方向信号") {
    if ((profile.directionalWinRatePct || 0) >= 55 && profile.avgRouteReturnPct > 0) return "绿灯";
    if ((profile.directionalWinRatePct || 0) >= 50) return "黄灯";
    return "红灯";
  }

  if (profile.signalType === "波动方向信号") {
    if (profile.successRatePct >= 62 && (profile.directionalWinRatePct || 0) >= 53) return "绿灯";
    if (profile.successRatePct >= 55) return "黄灯";
    return "红灯";
  }

  if (profile.signalType === "位置回归信号") {
    if (profile.successRatePct >= 70 && profile.avgRouteReturnPct > 0.5) return "绿灯";
    if (profile.successRatePct >= 58) return "黄灯";
    return "红灯";
  }

  if (profile.signalType === "震荡状态信号") {
    if (profile.successRatePct >= 72 && Math.abs(profile.avgFutureReturnPct) <= 0.8) return "绿灯";
    if (profile.successRatePct >= 65) return "黄灯";
    return "红灯";
  }

  if (profile.signalType === "风险过滤信号") {
    if (profile.successRatePct >= 62) return "黄灯";
    return "观察";
  }

  return "观察";
}

function buildStateProfileSplit(assignedRows, config, cleanPayload) {
  const trainTo = config.stateProfileTrainTo || DEFAULT_PROFILE_TRAIN_TO;
  const validateFrom = config.stateProfileValidateFrom || DEFAULT_PROFILE_VALIDATE_FROM;
  const validateTo = config.stateProfileValidateTo || config.toDate || cleanPayload.metadata.lastDate || assignedRows.at(-1)?.date || "";
  const trainRows = assignedRows.filter((row) => inDateRange(row.date, "", trainTo));
  const validationRows = assignedRows.filter((row) => inDateRange(row.date, validateFrom, validateTo));

  return {
    mode: "calendar_holdout",
    trainTo,
    validateFrom,
    validateTo,
    trainFrom: trainRows[0]?.date || "",
    trainRows: trainRows.length,
    validationRows: validationRows.length
  };
}

function groupStateRouteRows(routerRows, stateIdByDate, from, to) {
  const groups = new Map();

  for (const row of routerRows) {
    if (!inDateRange(row.date, from, to)) continue;
    const stateId = stateIdByDate.get(row.date);
    if (stateId === undefined) continue;
    const key = `${stateId}::${row.routeKey}::${row.horizon}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }

  return groups;
}

function buildStateRouteProfiles(routerRows, stateIdByDate, split) {
  const trainGroups = groupStateRouteRows(routerRows, stateIdByDate, "", split.trainTo);
  const validationGroups = groupStateRouteRows(routerRows, stateIdByDate, split.validateFrom, split.validateTo);
  const keys = new Set([...trainGroups.keys(), ...validationGroups.keys()]);

  const profiles = Array.from(keys).flatMap((key) => {
    const [stateId] = key.split("::");
    const trainRows = trainGroups.get(key) || [];
    const validationRows = validationGroups.get(key) || [];
    const trainProfile = trainRows.length ? summarizeRouteGroup(trainRows) : null;
    const validationProfile = validationRows.length ? summarizeRouteGroup(validationRows) : null;
    const profile = validationProfile || trainProfile;

    if (!profile) return [];

    const light = validationProfile ? routeLight(validationProfile) : "验证不足";
    return [{
      stateId: Number(stateId),
      ...profile,
      light,
      profileScope: validationProfile ? "validate" : "train_only",
      trainOccurrences: trainProfile?.occurrences || 0,
      validateOccurrences: validationProfile?.occurrences || 0,
      trainSuccessRatePct: trainProfile?.successRatePct ?? "",
      validateSuccessRatePct: validationProfile?.successRatePct ?? "",
      trainDirectionalWinRatePct: trainProfile?.directionalWinRatePct ?? "",
      validateDirectionalWinRatePct: validationProfile?.directionalWinRatePct ?? "",
      trainAvgRouteReturnPct: trainProfile?.avgRouteReturnPct ?? "",
      validateAvgRouteReturnPct: validationProfile?.avgRouteReturnPct ?? "",
      rankScore: routeRankScore(profile, light)
    }];
  });

  const byState = new Map();
  for (const profile of profiles) {
    if (!byState.has(profile.stateId)) byState.set(profile.stateId, []);
    byState.get(profile.stateId).push(profile);
  }

  for (const [stateId, stateProfiles] of byState.entries()) {
    byState.set(stateId, stateProfiles.sort((left, right) => right.rankScore - left.rankScore));
  }

  return {
    profiles,
    byState
  };
}

function routeRankScore(profile, light) {
  const lightBonus = light === "绿灯" ? 30 : light === "黄灯" ? 15 : light === "样本少" ? -10 : 0;
  const directionalScore = profile.directionalWinRatePct === null ? 0 : profile.directionalWinRatePct - 50;
  return (
    lightBonus +
    (profile.avgScore * 0.18) +
    (profile.successRatePct * 0.45) +
    (directionalScore * 0.55) +
    Math.max(-15, Math.min(15, profile.avgRouteReturnPct * 2))
  );
}

function compactRouteProfile(profile) {
  return {
    routeKey: profile.routeKey,
    routeLabel: profile.routeLabel,
    light: profile.light,
    signalType: profile.signalType,
    horizon: profile.horizon,
    occurrences: profile.occurrences,
    avgScore: round(profile.avgScore, 2),
    successRatePct: round(profile.successRatePct, 2),
    directionalWinRatePct: profile.directionalWinRatePct === null ? "" : round(profile.directionalWinRatePct, 2),
    avgRouteReturnPct: round(profile.avgRouteReturnPct),
    avgFutureReturnPct: round(profile.avgFutureReturnPct),
    profileScope: profile.profileScope,
    trainOccurrences: profile.trainOccurrences,
    validateOccurrences: profile.validateOccurrences,
    trainSuccessRatePct: profile.trainSuccessRatePct === "" ? "" : round(profile.trainSuccessRatePct, 2),
    validateSuccessRatePct: profile.validateSuccessRatePct === "" ? "" : round(profile.validateSuccessRatePct, 2),
    trainDirectionalWinRatePct: profile.trainDirectionalWinRatePct === "" || profile.trainDirectionalWinRatePct === null ? "" : round(profile.trainDirectionalWinRatePct, 2),
    validateDirectionalWinRatePct: profile.validateDirectionalWinRatePct === "" || profile.validateDirectionalWinRatePct === null ? "" : round(profile.validateDirectionalWinRatePct, 2),
    trainAvgRouteReturnPct: profile.trainAvgRouteReturnPct === "" ? "" : round(profile.trainAvgRouteReturnPct),
    validateAvgRouteReturnPct: profile.validateAvgRouteReturnPct === "" ? "" : round(profile.validateAvgRouteReturnPct),
    rankScore: round(profile.rankScore, 2)
  };
}

function assignmentCsvRow(row, state) {
  return {
    date: row.date,
    stateId: state.id,
    stateName: state.name,
    confidence: round(row.assignment.confidence, 4),
    distance: round(row.assignment.distance, 4),
    close: round(row.close, 2),
    volatilityMultiple: round(row.values.volatilityMultiple),
    volumeMultiple: round(row.values.volumeMultiple),
    trendScore: round(row.values.trendScore),
    resonanceCount: round(row.values.resonanceCount),
    middleDeviationRate: round(row.values.middleDeviationRate),
    middleDeviationAtr: round(row.values.middleDeviationAtr),
    middlePositionPct: round(row.values.middlePositionPct),
    maDeviationRate: round(row.values.maDeviationRate),
    maDeviationAtr: round(row.values.maDeviationAtr),
    maPositionPct: round(row.values.maPositionPct),
    stretchHeat: round(row.values.stretchHeat)
  };
}

function stateCsvRow(state) {
  return {
    stateId: state.id,
    stateName: state.name,
    occurrences: state.occurrences,
    sharePct: round(state.sharePct, 2),
    avgConfidence: round(state.avgConfidence, 4),
    avgDistance: round(state.avgDistance, 4),
    firstSeen: state.firstSeen,
    lastSeen: state.lastSeen,
    typicalDates: state.typicalDates.map((item) => item.date).join(" | "),
    topFeatures: state.topFeatures.map((feature) => `${feature.label}:${round(feature.z, 2)}`).join(" | "),
    volatilityMultiple: round(state.profile.volatilityMultiple),
    volumeMultiple: round(state.profile.volumeMultiple),
    trendScore: round(state.profile.trendScore),
    resonanceCount: round(state.profile.resonanceCount),
    middleDeviationAtr: round(state.profile.middleDeviationAtr),
    maDeviationAtr: round(state.profile.maDeviationAtr),
    stretchHeat: round(state.profile.stretchHeat),
    weatherProfile: state.weatherProfile.slice(0, 8).map((item) => `${item.dimension}:${item.label} ${round(item.sharePct, 0)}%`).join(" | "),
    topStrategyRoutes: state.strategyProfile.slice(0, 5).map((item) => `${item.routeLabel}:${item.light}/${item.profileScope}/${item.horizon}日/${round(item.successRatePct, 0)}%`).join(" | ")
  };
}

function stateStrategyCsvRows(states) {
  return states.flatMap((state) => state.strategyProfile.map((profile) => ({
    stateId: state.id,
    stateName: state.name,
    routeLabel: profile.routeLabel,
    routeKey: profile.routeKey,
    light: profile.light,
    signalType: profile.signalType,
    horizon: profile.horizon,
    occurrences: profile.occurrences,
    avgScore: profile.avgScore,
    successRatePct: profile.successRatePct,
    directionalWinRatePct: profile.directionalWinRatePct,
    avgRouteReturnPct: profile.avgRouteReturnPct,
    avgFutureReturnPct: profile.avgFutureReturnPct,
    profileScope: profile.profileScope,
    trainOccurrences: profile.trainOccurrences,
    validateOccurrences: profile.validateOccurrences,
    trainSuccessRatePct: profile.trainSuccessRatePct,
    validateSuccessRatePct: profile.validateSuccessRatePct,
    trainDirectionalWinRatePct: profile.trainDirectionalWinRatePct,
    validateDirectionalWinRatePct: profile.validateDirectionalWinRatePct,
    trainAvgRouteReturnPct: profile.trainAvgRouteReturnPct,
    validateAvgRouteReturnPct: profile.validateAvgRouteReturnPct,
    rankScore: profile.rankScore
  })));
}

export function trainMarketStateModel(cleanPayload, config) {
  const { snapshots, dataset } = buildFeatureFactoryDataset(cleanPayload, config);
  const vectors = dataset.rows.map((row) => row.vector);

  if (vectors.length < config.stateModel.rows * config.stateModel.cols * 4) {
    throw new Error("状态训练样本太少，无法稳定训练 SOM");
  }

  const som = trainSom(vectors, config.stateModel);
  const assignedRows = dataset.rows.map((row) => {
    const assignment = assignSom(som, row.vector);
    return {
      ...row,
      assignment: {
        stateId: assignment.index,
        distance: assignment.distance,
        secondDistance: assignment.secondDistance,
        confidence: confidence(assignment.distance, assignment.secondDistance)
      }
    };
  });
  const stateIdByDate = new Map(assignedRows.map((row) => [row.date, row.assignment.stateId]));
  const routerBacktest = runStrategyRouterBacktest(cleanPayload, config);
  const stateProfileSplit = buildStateProfileSplit(assignedRows, config, cleanPayload);
  const stateRouteProfiles = buildStateRouteProfiles(routerBacktest.observationRows, stateIdByDate, stateProfileSplit);

  const stateRows = new Map();
  for (const row of assignedRows) {
    if (!stateRows.has(row.assignment.stateId)) stateRows.set(row.assignment.stateId, []);
    stateRows.get(row.assignment.stateId).push(row);
  }

  const states = Array.from({ length: som.weights.length }, (_, id) => {
    const rows = stateRows.get(id) || [];
    const profile = meanFeatureValues(rows);
    const zValues = zProfile(profile, dataset.stats);
    const node = som.weights[id];
    const topFeatures = strongestFeatures(zValues, 6);
    const strategyProfile = (stateRouteProfiles.byState.get(id) || []).map(compactRouteProfile);

    return {
      id,
      grid: `${node.row},${node.col}`,
      name: rows.length ? nameState(profile) : "未占用状态",
      occurrences: rows.length,
      sharePct: safeDivide(rows.length, assignedRows.length) * 100,
      avgConfidence: average(rows.map((row) => row.assignment.confidence)),
      avgDistance: average(rows.map((row) => row.assignment.distance)),
      firstSeen: rows[0]?.date || "",
      lastSeen: rows.at(-1)?.date || "",
      typicalDates: typicalRows(rows),
      topFeatures,
      weatherProfile: weatherProfile(rows, config),
      strategyProfile,
      profile,
      zProfile: zValues
    };
  }).sort((left, right) => right.occurrences - left.occurrences);

  const statesById = new Map(states.map((state) => [state.id, state]));
  const decisionTree = trainDecisionTree(
    assignedRows.map((row) => ({
      values: row.values,
      label: row.assignment.stateId
    })),
    dataset.features,
    {
      ...config.decisionTree,
      classNames: Object.fromEntries(states.map((state) => [state.id, `S${state.id} ${state.name}`]))
    }
  );
  const latest = assignedRows.at(-1);
  const currentState = latest ? statesById.get(latest.assignment.stateId) : null;
  const assignmentRows = assignedRows.map((row) => assignmentCsvRow(row, statesById.get(row.assignment.stateId)));

  return {
    metadata: {
      instrument: cleanPayload.metadata.instrument,
      bar: cleanPayload.metadata.bar,
      firstDate: snapshots[0]?.date || null,
      lastDate: snapshots.at(-1)?.date || null,
      snapshotCount: snapshots.length,
      featureCount: dataset.features.length,
      stateCount: som.weights.length,
      quantizationError: round(som.quantizationError, 6),
      featureNormalizationMode: dataset.normalization?.mode || "unknown",
      stateStrategyProfileMode: "train_validate_split",
      stateStrategyProfileSplit: stateProfileSplit,
      stateStrategyProfileNote: "Route lights prefer validation-slice outcomes. Train-slice values are retained as background context.",
      decisionTreeNote: "The state decision tree explains SOM state assignment; it is not an out-of-sample directional predictor.",
      generatedAt: new Date().toISOString(),
      model: {
        type: "SOM",
        rows: config.stateModel.rows,
        cols: config.stateModel.cols,
        epochs: config.stateModel.epochs,
        seed: config.stateModel.seed
      }
    },
    features: dataset.features,
    featureStats: dataset.stats,
    decisionTree,
    states,
    currentState: currentState ? {
      id: currentState.id,
      name: currentState.name,
      date: latest.date,
      confidence: round(latest.assignment.confidence, 4),
      distance: round(latest.assignment.distance, 4),
      topFeatures: currentState.topFeatures,
      weatherProfile: currentState.weatherProfile,
      strategyProfile: currentState.strategyProfile.slice(0, 8),
      profile: currentState.profile
    } : null,
    assignmentRows,
    stateRows: states.map(stateCsvRow),
    stateStrategyRows: stateStrategyCsvRows(states),
    decisionRuleRows: decisionTreeRuleRows(decisionTree),
    decisionImportanceRows: decisionTreeImportanceRows(decisionTree)
  };
}
