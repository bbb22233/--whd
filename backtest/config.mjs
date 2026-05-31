export const defaultConfig = {
  instrument: "BTC-USDT-SWAP",
  bar: "1D",
  days: 1200,
  requestLimit: 100,
  fromDate: null,
  toDate: null,
  indicator: {
    atrPeriod: 14,
    fibAtrPeriods: [3, 8, 13, 21],
    volumeMaPeriod: 20,
    middlePeriod: 21,
    maPeriod: 233,
    momentumPeriods: [8, 13, 21, 34],
    trendWeights: {
      8: 0.35,
      13: 0.3,
      21: 0.22,
      34: 0.13
    }
  },
  thresholds: {
    strongTrendPct: 3,
    weakTrendPct: 1.2,
    volatilityBreakout: 1.2,
    volumeExpansion: 1.5,
    hotPct: 85,
    coldPct: 15,
    divergencePct: 1,
    quietTrendPct: 1.2
  },
  stateModel: {
    rows: 3,
    cols: 3,
    epochs: 700,
    seed: 20260530,
    learningRate: 0.45
  },
  decisionTree: {
    maxDepth: 4,
    minSamplesSplit: 90,
    minSamplesLeaf: 35,
    minGain: 0.006,
    maxThresholds: 12
  },
  horizons: [1, 3, 5, 10]
};

export function parseArgs(argv, config = defaultConfig) {
  const next = structuredClone(config);

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const value = argv[index + 1];

    if (arg === "--instrument" && value) {
      next.instrument = value;
      index += 1;
    } else if (arg === "--bar" && value) {
      next.bar = value;
      index += 1;
    } else if (arg === "--days" && value) {
      next.days = Number(value);
      index += 1;
    } else if (arg === "--limit" && value) {
      next.requestLimit = Number(value);
      index += 1;
    } else if (arg === "--from" && value) {
      next.fromDate = value;
      index += 1;
    } else if (arg === "--to" && value) {
      next.toDate = value;
      index += 1;
    } else if (arg === "--states" && value) {
      const states = Number(value);
      next.stateModel.rows = 1;
      next.stateModel.cols = Math.max(2, Math.floor(states));
      index += 1;
    } else if (arg === "--epochs" && value) {
      next.stateModel.epochs = Number(value);
      index += 1;
    }
  }

  return next;
}

export function fileStem(config) {
  return `${config.instrument.replaceAll("-", "_")}_${config.bar}`;
}

export function reportStem(config) {
  const suffix = [
    config.fromDate ? `from_${config.fromDate}` : null,
    config.toDate ? `to_${config.toDate}` : null
  ].filter(Boolean).join("_");

  return suffix ? `${fileStem(config)}_${suffix}` : fileStem(config);
}
