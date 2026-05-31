function finite(value) {
  return Number.isFinite(value);
}

function round(value, digits = 4) {
  if (!finite(value)) return 0;
  return Number(value.toFixed(digits));
}

function probabilityEdge(left, right) {
  return Math.abs((Number(left) || 0) - (Number(right) || 0));
}

function confidenceLabel(samples, edgePct) {
  if (samples < 120) return "样本偏少";
  if (edgePct >= 30) return "强";
  if (edgePct >= 18) return "中强";
  if (edgePct >= 10) return "中";
  return "弱";
}

function roleForKind(kindKey) {
  if (kindKey === "middle") return "短期拉伸/回归";
  return "大周期天气过滤";
}

function ruleForState(row) {
  const state = row.state || "";
  const isMiddle = row.kindKey === "middle";
  const isMa = row.kindKey === "ma233";
  const edge = probabilityEdge(row.returnCloserProbabilityPct, row.continueAwayProbabilityPct);
  const confidence = confidenceLabel(row.occurrences, edge);

  if (isMiddle && state.includes("下侧极端")) {
    return {
      weatherTag: "短期过冷",
      ruleSignal: "回归倾向强",
      ruleUse: "适合观察反弹/空头止盈，不直接等于大趋势转多",
      riskNote: "如果大周期仍弱，只能当短线天气看"
    };
  }

  if (isMiddle && state.includes("上侧极端")) {
    return {
      weatherTag: "短期过热",
      ruleSignal: "回落倾向强",
      ruleUse: "适合观察追多降温/多头止盈，不直接等于做空信号",
      riskNote: "强趋势里极端可以延续，必须看波动和量能"
    };
  }

  if (isMiddle && state.includes("下侧偏离")) {
    return {
      weatherTag: "短期下侧偏离",
      ruleSignal: confidence === "弱" ? "轻微回归倾向" : "回归倾向",
      ruleUse: "只做观察项，等待更极端或其他指标共振",
      riskNote: "优势不够大，不能单独触发策略"
    };
  }

  if (isMiddle && state.includes("上侧偏离")) {
    return {
      weatherTag: "短期上侧偏离",
      ruleSignal: confidence === "弱" ? "轻微回落倾向" : "回落倾向",
      ruleUse: "只做观察项，等待更极端或其他指标共振",
      riskNote: "优势不够大，不能单独触发策略"
    };
  }

  if (isMiddle && state.includes("贴近")) {
    return {
      weatherTag: "短期贴近中轴",
      ruleSignal: "方向信息弱",
      ruleUse: "不做均值回归依据，更多看波动是否扩张",
      riskNote: "贴近中轴时继续拉伸概率通常更高"
    };
  }

  if (isMa && state.includes("下侧极端")) {
    return {
      weatherTag: "大周期弱势深水区",
      ruleSignal: "风险过滤",
      ruleUse: "禁止仅凭超跌当买点，低吸必须等短期指标和波动确认",
      riskNote: "历史上继续远离 233MA 的概率不低"
    };
  }

  if (isMa && state.includes("上侧极端")) {
    return {
      weatherTag: "大周期强势高位",
      ruleSignal: "趋势过滤",
      ruleUse: "不把高乖离直接当做空信号，更多提示追高风险",
      riskNote: "强势区可以长期维持在 233MA 上方"
    };
  }

  if (isMa && state.includes("下侧偏离")) {
    return {
      weatherTag: "大周期偏弱",
      ruleSignal: "谨慎过滤",
      ruleUse: "趋势多头降权，反弹策略需要更严格确认",
      riskNote: "未到极端，但大天气仍偏弱"
    };
  }

  if (isMa && state.includes("上侧偏离")) {
    return {
      weatherTag: "大周期偏强",
      ruleSignal: "顺势过滤",
      ruleUse: "趋势策略可加权，均值回落只当降温提示",
      riskNote: "不是天然做空区域"
    };
  }

  return {
    weatherTag: "大周期中轴附近",
    ruleSignal: "方向切换区",
    ruleUse: "不做趋势天气判断，等待方向重新拉开",
    riskNote: "中轴附近容易出现反复"
  };
}

function ruleLibraryRow(row) {
  const rule = ruleForState(row);
  const edge = probabilityEdge(row.returnCloserProbabilityPct, row.continueAwayProbabilityPct);

  return {
    kind: row.kind,
    kindKey: row.kindKey,
    role: roleForKind(row.kindKey),
    state: row.state,
    horizon: row.horizon,
    weatherTag: rule.weatherTag,
    ruleSignal: rule.ruleSignal,
    ruleUse: rule.ruleUse,
    riskNote: rule.riskNote,
    confidence: confidenceLabel(row.occurrences, edge),
    probabilityEdgePct: round(edge, 2),
    occurrences: row.occurrences,
    medianDeviationRate: row.medianDeviationRate,
    medianDeviationAtr: row.medianDeviationAtr,
    medianPositionPct: row.medianPositionPct,
    returnCloserProbabilityPct: row.returnCloserProbabilityPct,
    continueAwayProbabilityPct: row.continueAwayProbabilityPct,
    crossBaselineProbabilityPct: row.crossBaselineProbabilityPct,
    reversionDirectionHitPct: row.reversionDirectionHitPct,
    atrUpProbabilityPct: row.atrUpProbabilityPct,
    atrDownProbabilityPct: row.atrDownProbabilityPct,
    medianDistanceChangeAtr: row.medianDistanceChangeAtr,
    avgReturnPct: row.avgReturnPct
  };
}

function currentRuleRow(row) {
  const rule = ruleForState(row);
  const edge = probabilityEdge(row.returnCloserProbabilityPct, row.continueAwayProbabilityPct);

  return {
    date: row.date,
    close: row.close,
    kind: row.kind,
    kindKey: row.kindKey,
    role: roleForKind(row.kindKey),
    state: row.state,
    horizon: row.horizon,
    weatherTag: rule.weatherTag,
    ruleSignal: rule.ruleSignal,
    ruleUse: rule.ruleUse,
    riskNote: rule.riskNote,
    confidence: confidenceLabel(row.similarOccurrences, edge),
    probabilityEdgePct: round(edge, 2),
    deviationRate: row.deviationRate,
    deviationAtr: row.deviationAtr,
    positionPct: row.positionPct,
    historicalRateRankPct: row.historicalRateRankPct,
    historicalAtrRankPct: row.historicalAtrRankPct,
    historicalPositionRankPct: row.historicalPositionRankPct,
    similarOccurrences: row.similarOccurrences,
    returnCloserProbabilityPct: row.returnCloserProbabilityPct,
    continueAwayProbabilityPct: row.continueAwayProbabilityPct,
    crossBaselineProbabilityPct: row.crossBaselineProbabilityPct,
    reversionDirectionHitPct: row.reversionDirectionHitPct,
    atrUpProbabilityPct: row.atrUpProbabilityPct,
    atrDownProbabilityPct: row.atrDownProbabilityPct,
    avgAtrChangePct: row.avgAtrChangePct,
    medianDistanceChangeAtr: row.medianDistanceChangeAtr
  };
}

function findCurrent(currentRows, kindKey, horizon) {
  return currentRows.find((row) => row.kindKey === kindKey && row.horizon === horizon);
}

function finalWeather(currentRows) {
  const middle10 = findCurrent(currentRows, "middle", 10);
  const ma10 = findCurrent(currentRows, "ma233", 10);
  if (!middle10 || !ma10) {
    return {
      weather: "数据不足",
      shortTerm: "未知",
      bigCycle: "未知",
      actionBias: "等待数据补齐"
    };
  }

  const middleRule = ruleForState(middle10);
  const maRule = ruleForState(ma10);
  const middleEdge = probabilityEdge(middle10.returnCloserProbabilityPct, middle10.continueAwayProbabilityPct);
  const maEdge = probabilityEdge(ma10.returnCloserProbabilityPct, ma10.continueAwayProbabilityPct);
  const shortBias = middle10.returnCloserProbabilityPct > middle10.continueAwayProbabilityPct
    ? "短期略偏回归"
    : "短期仍可能继续拉伸";
  const bigBias = ma10.state.includes("下侧")
    ? "大周期偏弱"
    : ma10.state.includes("上侧")
      ? "大周期偏强"
      : "大周期中性";
  const isWeakBigCycle = ma10.state.includes("下侧极端") || ma10.state.includes("下侧偏离");
  const isMiddleExtreme = middle10.state.includes("极端");

  let actionBias = "观察";
  let gate = "黄灯";

  if (isWeakBigCycle && !isMiddleExtreme) {
    actionBias = "不把短期下偏当买点，等待更强共振";
    gate = "黄偏红";
  } else if (isWeakBigCycle && isMiddleExtreme && middle10.state.includes("下侧")) {
    actionBias = "可观察短线回归，但仍受大周期弱势约束";
    gate = "黄灯";
  } else if (!isWeakBigCycle && isMiddleExtreme) {
    actionBias = "短期回归信号更干净";
    gate = "黄偏绿";
  }

  return {
    date: middle10.date,
    close: middle10.close,
    weather: `${middleRule.weatherTag} + ${maRule.weatherTag}`,
    shortTerm: `${shortBias}，10日回归概率 ${middle10.returnCloserProbabilityPct}%`,
    bigCycle: `${bigBias}，10日继续远离概率 ${ma10.continueAwayProbabilityPct}%`,
    gate,
    actionBias,
    ruleConfidence: `中值${confidenceLabel(middle10.similarOccurrences, middleEdge)} / 233MA${confidenceLabel(ma10.similarOccurrences, maEdge)}`,
    riskNote: `${middleRule.riskNote}；${maRule.riskNote}`
  };
}

export function buildDeviationRules(deviationStudyResult) {
  const ruleLibraryRows = deviationStudyResult.stateSummaryRows.map(ruleLibraryRow);
  const currentRuleRows = deviationStudyResult.currentRows.map(currentRuleRow);

  return {
    metadata: {
      ...deviationStudyResult.metadata,
      generatedAt: new Date().toISOString(),
      rulePrinciple: "中值乖离负责短期拉伸/回归，233MA乖离负责大周期天气过滤。规则只识别状态，不直接给交易方向。"
    },
    finalWeather: finalWeather(currentRuleRows),
    currentRuleRows,
    ruleLibraryRows
  };
}
