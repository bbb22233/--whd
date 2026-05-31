function finite(value) {
  return Number.isFinite(value);
}

function clamp(value, min, max) {
  if (!finite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function round(value, digits = 2) {
  if (!finite(value)) return 0;
  return Number(value.toFixed(digits));
}

function labelByDimension(labels, dimension) {
  return labels.find((label) => label.dimension === dimension);
}

function scoreReason(label, condition) {
  return condition ? label : null;
}

function compactReasons(reasons) {
  return reasons.filter(Boolean);
}

function route(key, label, family, direction, score, reasons) {
  return {
    key,
    label,
    family,
    direction,
    score: round(clamp(score, 0, 100)),
    reasons: compactReasons(reasons)
  };
}

export function routeStrategies(snapshot, labels) {
  const volatilityLabel = labelByDimension(labels, "波动")?.label || "";
  const middleLabel = labelByDimension(labels, "中值位置")?.label || "";
  const maLabel = labelByDimension(labels, "MA位置")?.label || "";
  const trendLabel = labelByDimension(labels, "趋势")?.label || "";
  const volumeLabel = labelByDimension(labels, "量能")?.label || "";
  const energyLabel = labelByDimension(labels, "动能")?.label || "";
  const shortVolLabel = labelByDimension(labels, "短波动")?.label || "";
  const trendScore = snapshot.momentum.trendScore;
  const absTrend = Math.abs(trendScore);
  const resonance = snapshot.momentum.resonanceCount;
  const trendDirection = snapshot.momentum.resonanceDirection;
  const middleDeviation = snapshot.position.middleDeviationAtr;
  const maDeviation = snapshot.position.maDeviationAtr;
  const middleAbs = Math.abs(middleDeviation);
  const volumeMultiple = snapshot.volume.multiple;
  const atrPercentile = snapshot.volatility.atrPercentile;
  const multiplePercentile = snapshot.volatility.multiplePercentile;
  const volatilityMultiple = snapshot.volatility.multiple;
  const atr3To21 = snapshot.volatility.fibAtrComparisons.atr3To21;
  const atr8To21 = snapshot.volatility.fibAtrComparisons.atr8To21;
  const compressed = volatilityLabel === "波动压缩";
  const highExpansion = volatilityLabel === "高波动扩张";
  const highCooling = volatilityLabel === "高波动冷却";
  const shortHeating = shortVolLabel === "短波动升温" || (atr3To21 >= 1.08 && atr8To21 >= 1);
  const shortCooling = shortVolLabel === "短波动降温" || (atr3To21 <= 0.88 && atr8To21 <= 0.96);
  const strongUp = trendDirection === "up" && trendScore > 0 && resonance >= 3;
  const strongDown = trendDirection === "down" && trendScore < 0 && resonance >= 3;
  const middleUpperExtreme = middleLabel.includes("上侧极端");
  const middleLowerExtreme = middleLabel.includes("下侧极端");
  const middleUpper = middleDeviation > 0.35;
  const middleLower = middleDeviation < -0.35;
  const maUpperExtreme = maLabel.includes("上侧极端");
  const maLowerExtreme = maLabel.includes("下侧极端");
  const lowTrend = absTrend < 1.2;
  const normalVolume = volumeMultiple >= 0.75 && volumeMultiple <= 1.2;

  const trendBase = 12 + (resonance * 10) + Math.min(absTrend * 5, 32) + (volumeMultiple >= 1.15 ? 8 : 0);
  const trendLong = trendBase +
    (strongUp ? 22 : 0) -
    (strongDown ? 38 : 0) -
    (compressed ? 8 : 0) -
    (middleUpperExtreme ? 10 : 0) -
    (maLowerExtreme ? 14 : 0);
  const trendShort = trendBase +
    (strongDown ? 22 : 0) -
    (strongUp ? 38 : 0) -
    (compressed ? 24 : 0) -
    (shortCooling ? 14 : 0) -
    (middleLowerExtreme ? 12 : 0) -
    (maLowerExtreme ? 10 : 0) -
    (maUpperExtreme ? 14 : 0);

  const breakoutBase = 18 +
    (compressed ? 16 : 0) +
    (shortHeating ? 24 : 0) +
    (multiplePercentile >= 70 ? 20 : 0) +
    (volumeMultiple >= 1.2 ? 10 : 0) -
    (shortCooling ? 12 : 0) -
    (highCooling ? 16 : 0);
  const breakoutUp = breakoutBase +
    (strongUp ? 18 : 0) -
    (strongDown ? 12 : 0) +
    (maDeviation > 0 ? 8 : -8) +
    (middleDeviation > 0 ? 5 : -5);
  const breakoutDown = breakoutBase +
    (strongDown ? 18 : 0) -
    (strongUp ? 12 : 0) +
    (maDeviation < 0 ? 8 : -8) +
    (middleDeviation < 0 ? 5 : -5);

  const reversionBase = 12 +
    clamp((middleAbs - 0.75) * 18, 0, 34) +
    (compressed || shortCooling ? 8 : 0) -
    (highExpansion ? 8 : 0);
  const meanReversionLong = reversionBase +
    (middleLower ? 24 : -18) +
    (middleLowerExtreme ? 18 : 0) +
    (maLowerExtreme ? 8 : 0) -
    (strongDown ? 12 : 0);
  const meanReversionShort = reversionBase +
    (middleUpper ? 24 : -18) +
    (middleUpperExtreme ? 18 : 0) +
    (maUpperExtreme ? 8 : 0) -
    (strongUp ? 12 : 0);

  const gridNeutral = 38 +
    (atrPercentile <= 40 ? 16 : 0) +
    (volatilityMultiple <= 1 ? 14 : 0) +
    (lowTrend ? 22 : 0) +
    (normalVolume ? 8 : 0) -
    (highExpansion ? 30 : 0) -
    (absTrend >= 3 ? 24 : 0) -
    (middleAbs >= 1.3 ? 18 : 0) -
    ((maUpperExtreme || maLowerExtreme) ? 8 : 0);

  const maxDirectional = Math.max(trendLong, trendShort, breakoutUp, breakoutDown, meanReversionLong, meanReversionShort, gridNeutral);
  const waitDefense = 34 +
    (compressed ? 10 : 0) +
    (shortCooling ? 10 : 0) +
    ((maLowerExtreme || maUpperExtreme) ? 14 : 0) +
    ((energyLabel === "剩余动能不足") ? 6 : 0) +
    ((volumeLabel === "缩量") ? 6 : 0) +
    (maxDirectional < 45 ? 18 : 0) -
    (maxDirectional * 0.14);

  const routes = [
    route("trendLong", "趋势追多", "trend", "long", trendLong, [
      scoreReason("多周期趋势向上", strongUp),
      scoreReason("趋势向下，追多降权", strongDown),
      scoreReason("低波动压缩，趋势入场降权", compressed),
      scoreReason("价格在MA下侧极端，追多需等待修复", maLowerExtreme)
    ]),
    route("trendShort", "趋势做空", "trend", "short", trendShort, [
      scoreReason("多周期趋势向下", strongDown),
      scoreReason("趋势向上，追空降权", strongUp),
      scoreReason("低波动压缩，直接追空降权", compressed),
      scoreReason("短波动降温，直接追空降权", shortCooling),
      scoreReason("价格在MA上侧极端，追空需等待转弱", maUpperExtreme)
    ]),
    route("breakoutUp", "向上突破", "breakout", "long", breakoutUp, [
      scoreReason("波动压缩，具备等待突破结构", compressed),
      scoreReason("短周期ATR升温", shortHeating),
      scoreReason("放量或量能偏强", volumeMultiple >= 1.2),
      scoreReason("趋势下行，上破降权", strongDown)
    ]),
    route("breakoutDown", "向下突破", "breakout", "short", breakoutDown, [
      scoreReason("波动压缩，具备等待突破结构", compressed),
      scoreReason("短周期ATR升温", shortHeating),
      scoreReason("放量或量能偏强", volumeMultiple >= 1.2),
      scoreReason("趋势下行，下破顺势加权", strongDown)
    ]),
    route("meanReversionLong", "低吸均值回归", "meanReversion", "long", meanReversionLong, [
      scoreReason("中值下侧偏离", middleLower),
      scoreReason("中值下侧极端", middleLowerExtreme),
      scoreReason("短波动降温，回归环境加权", shortCooling),
      scoreReason("趋势强下行，低吸降权", strongDown)
    ]),
    route("meanReversionShort", "高抛均值回归", "meanReversion", "short", meanReversionShort, [
      scoreReason("中值上侧偏离", middleUpper),
      scoreReason("中值上侧极端", middleUpperExtreme),
      scoreReason("短波动降温，回归环境加权", shortCooling),
      scoreReason("趋势强上行，高抛降权", strongUp)
    ]),
    route("gridNeutral", "震荡网格", "grid", "neutral", gridNeutral, [
      scoreReason("ATR处于低位", atrPercentile <= 40),
      scoreReason("当日振幅未超过ATR", volatilityMultiple <= 1),
      scoreReason("趋势动能弱", lowTrend),
      scoreReason("趋势动能强，网格降权", absTrend >= 3)
    ]),
    route("waitDefense", "防守等待", "wait", "neutral", waitDefense, [
      scoreReason("波动压缩，等待确认", compressed),
      scoreReason("短波动降温", shortCooling),
      scoreReason("MA位置极端，等待结构修复", maLowerExtreme || maUpperExtreme),
      scoreReason("剩余动能不足", energyLabel === "剩余动能不足")
    ])
  ].sort((left, right) => right.score - left.score);

  const scoreMap = Object.fromEntries(routes.map((item) => [item.key, item.score]));
  const scores = {
    ...scoreMap,
    trendFollowing: round(Math.max(scoreMap.trendLong, scoreMap.trendShort)),
    breakout: round(Math.max(scoreMap.breakoutUp, scoreMap.breakoutDown)),
    meanReversion: round(Math.max(scoreMap.meanReversionLong, scoreMap.meanReversionShort)),
    grid: scoreMap.gridNeutral,
    wait: scoreMap.waitDefense
  };

  return {
    scores,
    routes,
    topRoutes: routes.slice(0, 3)
  };
}
