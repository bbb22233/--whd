function finite(value) {
  return Number.isFinite(value);
}

function safeDivide(numerator, denominator) {
  if (!finite(numerator) || !finite(denominator) || denominator === 0) return 0;
  return numerator / denominator;
}

function clamp(value, min, max) {
  if (!finite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function average(values) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function percentChange(current, previous) {
  return safeDivide(current - previous, previous) * 100;
}

function rollingSlice(values, endIndex, length) {
  return values.slice(Math.max(0, endIndex - length + 1), endIndex + 1);
}

function highLowMiddle(candles, endIndex, length) {
  const window = rollingSlice(candles, endIndex, length);
  if (window.length < length) return null;
  const high = Math.max(...window.map((candle) => candle.high));
  const low = Math.min(...window.map((candle) => candle.low));
  return (high + low) / 2;
}

function simpleMovingAverage(values, endIndex, length) {
  const window = rollingSlice(values, endIndex, length);
  if (window.length < length) return null;
  return average(window);
}

function trueRanges(candles) {
  return candles.map((candle, index) => {
    if (index === 0) return candle.high - candle.low;
    const previousClose = candles[index - 1].close;
    return Math.max(
      candle.high - candle.low,
      Math.abs(candle.high - previousClose),
      Math.abs(candle.low - previousClose)
    );
  });
}

function wilderAtr(candles, period) {
  const ranges = trueRanges(candles);
  const atrValues = Array(candles.length).fill(null);
  if (ranges.length < period) return atrValues;

  let previousAtr = average(ranges.slice(0, period));
  atrValues[period - 1] = previousAtr;

  for (let index = period; index < ranges.length; index += 1) {
    previousAtr = ((previousAtr * (period - 1)) + ranges[index]) / period;
    atrValues[index] = previousAtr;
  }

  return atrValues;
}

function deviationInAtr(price, baseline, atr) {
  if (!baseline || !atr) return null;
  const deviationRate = safeDivide(price - baseline, baseline);
  const atrRate = safeDivide(atr, baseline);
  return safeDivide(deviationRate, atrRate);
}

function positionPct(current, valley, peak) {
  if (!finite(current) || !finite(valley) || !finite(peak) || peak === valley) return 50;
  return clamp(((current - valley) / (peak - valley)) * 100, 0, 100);
}

function resonance(values) {
  const upCount = values.filter((value) => value > 0).length;
  const downCount = values.filter((value) => value < 0).length;

  if (upCount >= 3) return { direction: "up", count: upCount };
  if (downCount >= 3) return { direction: "down", count: downCount };
  return { direction: "mixed", count: Math.max(upCount, downCount) };
}

function prefixExtrema(values) {
  const peaks = Array(values.length).fill(null);
  const valleys = Array(values.length).fill(null);
  let peak = -Infinity;
  let valley = Infinity;

  values.forEach((value, index) => {
    if (finite(value)) {
      peak = Math.max(peak, value);
      valley = Math.min(valley, value);
    }

    peaks[index] = finite(peak) ? peak : null;
    valleys[index] = finite(valley) ? valley : null;
  });

  return { peaks, valleys };
}

function prefixPercentile(values) {
  const uniqueValues = [...new Set(values.filter(finite))].sort((left, right) => left - right);
  const ranks = new Map(uniqueValues.map((value, index) => [value, index + 1]));
  const tree = Array(uniqueValues.length + 2).fill(0);
  const result = [];
  let total = 0;

  function add(index, value) {
    for (let cursor = index; cursor < tree.length; cursor += cursor & -cursor) {
      tree[cursor] += value;
    }
  }

  function sum(index) {
    let totalAtIndex = 0;
    for (let cursor = index; cursor > 0; cursor -= cursor & -cursor) {
      totalAtIndex += tree[cursor];
    }
    return totalAtIndex;
  }

  for (const value of values) {
    if (!finite(value)) {
      result.push(null);
      continue;
    }

    const rank = ranks.get(value);
    add(rank, 1);
    total += 1;

    const less = sum(rank - 1);
    const equal = sum(rank) - less;
    result.push(((less + (equal * 0.5)) / total) * 100);
  }

  return result;
}

function buildAtrBundle(candles, period) {
  const atrValues = wilderAtr(candles, period);
  const atrPctValues = candles.map((candle, index) => atrValues[index] ? safeDivide(atrValues[index], candle.close) * 100 : null);
  const multipleValues = candles.map((candle, index) => atrValues[index] ? safeDivide(candle.high - candle.low, atrValues[index]) : null);

  return {
    period,
    atrValues,
    atrPctValues,
    atrPercentileValues: prefixPercentile(atrPctValues),
    multipleValues,
    multiplePercentileValues: prefixPercentile(multipleValues)
  };
}

export function buildIndicatorSnapshots(candles, config) {
  const { indicator } = config;
  const closes = candles.map((candle) => candle.close);
  const atrValues = wilderAtr(candles, indicator.atrPeriod);
  const atrPctValues = candles.map((candle, index) => atrValues[index] ? safeDivide(atrValues[index], candle.close) * 100 : null);
  const volatilityMultipleValues = candles.map((candle, index) => atrValues[index] ? safeDivide(candle.high - candle.low, atrValues[index]) : null);
  const atrPercentileValues = prefixPercentile(atrPctValues);
  const volatilityMultiplePercentileValues = prefixPercentile(volatilityMultipleValues);
  const fibAtrPeriods = indicator.fibAtrPeriods || [3, 8, 13, 21];
  const fibAtrBundles = Object.fromEntries(fibAtrPeriods.map((period) => [String(period), buildAtrBundle(candles, period)]));
  const middleValues = candles.map((_, index) => highLowMiddle(candles, index, indicator.middlePeriod));
  const maValues = candles.map((_, index) => simpleMovingAverage(closes, index, indicator.maPeriod));
  const middleDeviationAtrValues = candles.map((candle, index) => deviationInAtr(candle.close, middleValues[index], atrValues[index]));
  const maDeviationAtrValues = candles.map((candle, index) => deviationInAtr(candle.close, maValues[index], atrValues[index]));
  const middleExtrema = prefixExtrema(middleDeviationAtrValues);
  const maExtrema = prefixExtrema(maDeviationAtrValues);
  const maxMomentum = Math.max(...indicator.momentumPeriods);
  const warmup = Math.max(indicator.maPeriod - 1, indicator.middlePeriod - 1, indicator.atrPeriod - 1, maxMomentum);
  const snapshots = [];

  for (let index = warmup; index < candles.length; index += 1) {
    const latest = candles[index];
    const atrAbs = atrValues[index];
    const middle = middleValues[index];
    const ma233 = maValues[index];
    const middleDeviationAtr = middleDeviationAtrValues[index];
    const maDeviationAtr = maDeviationAtrValues[index];
    const middlePeakAtr = middleExtrema.peaks[index];
    const middleValleyAtr = middleExtrema.valleys[index];
    const maPeakAtr = maExtrema.peaks[index];
    const maValleyAtr = maExtrema.valleys[index];
    const atrPct = atrPctValues[index];
    const volatilityMultiple = volatilityMultipleValues[index];
    const atrPercentile = atrPercentileValues[index];
    const volatilityMultiplePercentile = volatilityMultiplePercentileValues[index];

    if (!atrAbs || !middle || !ma233 || middleDeviationAtr === null || maDeviationAtr === null) continue;
    if (atrPct === null || volatilityMultiple === null || atrPercentile === null || volatilityMultiplePercentile === null) continue;
    if (middlePeakAtr === null || middleValleyAtr === null || maPeakAtr === null || maValleyAtr === null) continue;

    const previousVolumes = candles.slice(Math.max(0, index - indicator.volumeMaPeriod), index).map((candle) => candle.volume);
    const volumeMa = average(previousVolumes);
    const momentumValues = Object.fromEntries(indicator.momentumPeriods.map((period) => [
      `d${period}`,
      percentChange(latest.close, candles[index - period].close)
    ]));
    const trendScore = indicator.momentumPeriods.reduce((sum, period) => {
      return sum + (momentumValues[`d${period}`] * (indicator.trendWeights[String(period)] || 0));
    }, 0);
    const resonanceState = resonance(indicator.momentumPeriods.map((period) => momentumValues[`d${period}`]));
    const middlePositionPct = positionPct(middleDeviationAtr, middleValleyAtr, middlePeakAtr);
    const maPositionPct = positionPct(maDeviationAtr, maValleyAtr, maPeakAtr);
    const rangeAbs = latest.high - latest.low;
    const rangePctClose = safeDivide(rangeAbs, latest.close) * 100;
    const remainingMomentumAbs = rangeAbs - atrAbs;
    const remainingMomentumPct = rangePctClose - atrPct;
    const remainingMomentumAtr = volatilityMultiple - 1;
    const fibAtr = Object.fromEntries(Object.entries(fibAtrBundles).flatMap(([period, bundle]) => {
      const fibAtrAbs = bundle.atrValues[index];
      const fibAtrPct = bundle.atrPctValues[index];
      const fibMultiple = bundle.multipleValues[index];
      const fibAtrPercentile = bundle.atrPercentileValues[index];
      const fibMultiplePercentile = bundle.multiplePercentileValues[index];
      if (!fibAtrAbs || fibAtrPct === null || fibMultiple === null || fibAtrPercentile === null || fibMultiplePercentile === null) return [];

      return [[period, {
        atrAbs: fibAtrAbs,
        atrPct: fibAtrPct,
        atrPercentile: fibAtrPercentile,
        multiple: fibMultiple,
        multiplePercentile: fibMultiplePercentile,
        remainingMomentumAbs: rangeAbs - fibAtrAbs,
        remainingMomentumPct: rangePctClose - fibAtrPct,
        remainingMomentumAtr: fibMultiple - 1
      }]];
    }));
    const fibAtrComparisons = {
      atr3To21: fibAtr["3"] && fibAtr["21"] ? safeDivide(fibAtr["3"].atrAbs, fibAtr["21"].atrAbs) : 0,
      atr8To21: fibAtr["8"] && fibAtr["21"] ? safeDivide(fibAtr["8"].atrAbs, fibAtr["21"].atrAbs) : 0,
      atr13To21: fibAtr["13"] && fibAtr["21"] ? safeDivide(fibAtr["13"].atrAbs, fibAtr["21"].atrAbs) : 0,
      atr3To8: fibAtr["3"] && fibAtr["8"] ? safeDivide(fibAtr["3"].atrAbs, fibAtr["8"].atrAbs) : 0,
      atr8To13: fibAtr["8"] && fibAtr["13"] ? safeDivide(fibAtr["8"].atrAbs, fibAtr["13"].atrAbs) : 0
    };

    snapshots.push({
      index,
      date: latest.date,
      openTime: latest.openTime,
      price: {
        last: latest.close,
        open: latest.open,
        high: latest.high,
        low: latest.low,
        changePct: percentChange(latest.close, latest.open)
      },
      volatility: {
        rangeAbs,
        rangePct: safeDivide(rangeAbs, latest.open) * 100,
        atrAbs,
        atrPct,
        atrPercentile,
        multiple: volatilityMultiple,
        multiplePercentile: volatilityMultiplePercentile,
        excess: volatilityMultiple - 1,
        remainingMomentumAbs,
        remainingMomentumPct,
        remainingMomentumAtr,
        fibAtr,
        fibAtrComparisons
      },
      volume: {
        current: latest.volume,
        ma20: volumeMa,
        multiple: safeDivide(latest.volume, volumeMa)
      },
      momentum: {
        ...momentumValues,
        trendScore,
        resonanceDirection: resonanceState.direction,
        resonanceCount: resonanceState.count
      },
      position: {
        middle,
        ma233,
        middleDeviationRate: safeDivide(latest.close - middle, middle) * 100,
        middleDeviationAtr,
        middlePeakAtr,
        middleValleyAtr,
        middlePositionPct,
        maDeviationRate: safeDivide(latest.close - ma233, ma233) * 100,
        maDeviationAtr,
        maPeakAtr,
        maValleyAtr,
        maPositionPct,
        stretchHeat: clamp(Math.abs(middlePositionPct - 50) + Math.abs(maPositionPct - 50), 0, 100)
      }
    });
  }

  return snapshots;
}
