import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs, reportStem } from "../backtest/config.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";
import { validateDecisionTrees } from "../backtest/decision-tree-validation.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const stem = fileStem(config);
const reportName = reportStem(config);
const inputPath = join(root, "data", "clean", `${stem}_clean.json`);
const macroPath = join(root, "data", "macro", `${stem}_macro_features.json`);
const comparisonJsonPath = join(root, "reports", `${reportName}_macro_impact_comparison.json`);
const comparisonCsvPath = join(root, "reports", `${reportName}_macro_impact_comparison.csv`);
const summaryCsvPath = join(root, "reports", `${reportName}_macro_impact_summary.csv`);

const QUALITY_RANK = new Map([
  ["弱参考", 0],
  ["观察", 1],
  ["强参考", 2]
]);

const KEEP_MACRO = "保留宏观";
const DROP_MACRO = "不保留宏观";
const SMALL_IMPACT = "宏观影响小";
const OBSERVE_ONLY = "仅观察";
const NO_MACRO_RESULT = "无宏观结果";

function parseValidationArgs(argv) {
  const options = {
    trainTo: "2023-12-31",
    validateFrom: "2024-01-01",
    validateTo: null
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const value = argv[index + 1];

    if (arg === "--train-to" && value) {
      options.trainTo = value;
      index += 1;
    } else if (arg === "--validate-from" && value) {
      options.validateFrom = value;
      index += 1;
    } else if (arg === "--validate-to" && value) {
      options.validateTo = value;
      index += 1;
    }
  }

  return options;
}

function finite(value) {
  return Number.isFinite(value);
}

function number(value) {
  const parsed = Number(value);
  return finite(parsed) ? parsed : 0;
}

function round(value, digits = 2) {
  if (!finite(value)) return 0;
  return Number(value.toFixed(digits));
}

function qualityRank(quality) {
  return QUALITY_RANK.get(quality) ?? 0;
}

function rowKey(row) {
  return [
    row.scope || "",
    row.regimeKey || "",
    row.treeType || "",
    row.horizon || "",
    row.routeKey || ""
  ].join("::");
}

function bestSignalLift(row) {
  if (!row) return 0;
  if (row.treeType === "策略适配树") {
    return Math.max(number(row.fitLiftPct), number(row.notFitLiftPct));
  }
  return number(row.accuracyLiftPct);
}

function bestSignalPrecision(row) {
  if (!row) return 0;
  if (row.treeType === "策略适配树") {
    return Math.max(number(row.fitPrecisionPct), number(row.notFitPrecisionPct));
  }
  return number(row.accuracyPct);
}

function macroDecision(technical, macro) {
  if (!macro) return NO_MACRO_RESULT;
  if (!technical) {
    return qualityRank(macro.validationQuality) > 0 && bestSignalLift(macro) >= 5 ? KEEP_MACRO : OBSERVE_ONLY;
  }

  const qualityDelta = qualityRank(macro.validationQuality) - qualityRank(technical.validationQuality);
  const liftDelta = bestSignalLift(macro) - bestSignalLift(technical);
  const precisionDelta = bestSignalPrecision(macro) - bestSignalPrecision(technical);

  if (macro.validationQuality === "弱参考" && technical.validationQuality !== "弱参考") return DROP_MACRO;
  if (qualityDelta < 0 && (liftDelta <= -3 || precisionDelta <= -3)) return DROP_MACRO;
  if (liftDelta <= -5 && precisionDelta <= 0) return DROP_MACRO;
  if (precisionDelta <= -5 && liftDelta <= 0) return DROP_MACRO;

  if (qualityDelta > 0 && macro.validationQuality !== "弱参考" && liftDelta >= 0 && precisionDelta >= -2) return KEEP_MACRO;
  if (qualityDelta > 0 && macro.validationQuality !== "弱参考" && precisionDelta >= 0 && liftDelta >= -2) return KEEP_MACRO;
  if (macro.validationQuality === "强参考" && liftDelta >= 3 && precisionDelta >= 0) return KEEP_MACRO;
  if (macro.validationQuality === "强参考" && precisionDelta >= 3 && liftDelta >= 0) return KEEP_MACRO;
  if (macro.validationQuality === "弱参考" && technical.validationQuality !== "弱参考") return DROP_MACRO;
  if (liftDelta >= 5 && precisionDelta >= 0 && macro.validationQuality !== "弱参考") return KEEP_MACRO;
  if (Math.abs(liftDelta) < 3 && Math.abs(precisionDelta) < 3) return SMALL_IMPACT;
  return OBSERVE_ONLY;
}

function comparisonRow(technical, macro) {
  const base = macro || technical;
  const decision = macroDecision(technical, macro);

  return {
    scope: base.scope,
    regimeKey: base.regimeKey || "",
    regimeLabel: base.regimeLabel || "",
    treeType: base.treeType,
    horizon: base.horizon,
    routeKey: base.routeKey || "",
    routeLabel: base.routeLabel || "",
    technicalQuality: technical?.validationQuality || "",
    macroQuality: macro?.validationQuality || "",
    technicalSamples: technical?.validationSamples || "",
    macroSamples: macro?.validationSamples || "",
    technicalAccuracyPct: technical?.accuracyPct ?? "",
    macroAccuracyPct: macro?.accuracyPct ?? "",
    deltaAccuracyPct: macro && technical ? round(number(macro.accuracyPct) - number(technical.accuracyPct)) : "",
    technicalAccuracyLiftPct: technical?.accuracyLiftPct ?? "",
    macroAccuracyLiftPct: macro?.accuracyLiftPct ?? "",
    deltaAccuracyLiftPct: macro && technical ? round(number(macro.accuracyLiftPct) - number(technical.accuracyLiftPct)) : "",
    technicalFitPrecisionPct: technical?.fitPrecisionPct ?? "",
    macroFitPrecisionPct: macro?.fitPrecisionPct ?? "",
    deltaFitPrecisionPct: macro && technical ? round(number(macro.fitPrecisionPct) - number(technical.fitPrecisionPct)) : "",
    technicalFitLiftPct: technical?.fitLiftPct ?? "",
    macroFitLiftPct: macro?.fitLiftPct ?? "",
    deltaFitLiftPct: macro && technical ? round(number(macro.fitLiftPct) - number(technical.fitLiftPct)) : "",
    technicalNotFitPrecisionPct: technical?.notFitPrecisionPct ?? "",
    macroNotFitPrecisionPct: macro?.notFitPrecisionPct ?? "",
    deltaNotFitPrecisionPct: macro && technical ? round(number(macro.notFitPrecisionPct) - number(technical.notFitPrecisionPct)) : "",
    technicalNotFitLiftPct: technical?.notFitLiftPct ?? "",
    macroNotFitLiftPct: macro?.notFitLiftPct ?? "",
    deltaNotFitLiftPct: macro && technical ? round(number(macro.notFitLiftPct) - number(technical.notFitLiftPct)) : "",
    technicalBestLiftPct: technical ? round(bestSignalLift(technical)) : "",
    macroBestLiftPct: macro ? round(bestSignalLift(macro)) : "",
    deltaBestLiftPct: macro && technical ? round(bestSignalLift(macro) - bestSignalLift(technical)) : "",
    technicalBestPrecisionPct: technical ? round(bestSignalPrecision(technical)) : "",
    macroBestPrecisionPct: macro ? round(bestSignalPrecision(macro)) : "",
    deltaBestPrecisionPct: macro && technical ? round(bestSignalPrecision(macro) - bestSignalPrecision(technical)) : "",
    decision,
    technicalReason: technical?.validationReason || "",
    macroReason: macro?.validationReason || ""
  };
}

function groupByKey(rows) {
  return new Map(rows.map((row) => [rowKey(row), row]));
}

function compareRows(technicalRows, macroRows) {
  const technicalByKey = groupByKey(technicalRows);
  const macroByKey = groupByKey(macroRows);
  const keys = Array.from(new Set([...technicalByKey.keys(), ...macroByKey.keys()]));

  return keys
    .map((key) => comparisonRow(technicalByKey.get(key), macroByKey.get(key)))
    .sort((left, right) =>
      left.scope.localeCompare(right.scope) ||
      left.regimeKey.localeCompare(right.regimeKey) ||
      left.treeType.localeCompare(right.treeType) ||
      number(left.horizon) - number(right.horizon) ||
      left.routeKey.localeCompare(right.routeKey)
    );
}

function summarizeComparison(rows) {
  const groups = new Map();

  for (const row of rows) {
    const key = `${row.scope}::${row.regimeLabel || "holdout"}::${row.decision}`;
    const item = groups.get(key) || {
      scope: row.scope,
      regimeLabel: row.regimeLabel || "holdout",
      decision: row.decision,
      count: 0,
      avgDeltaBestLiftPct: 0,
      avgDeltaBestPrecisionPct: 0
    };
    item.count += 1;
    item.avgDeltaBestLiftPct += number(row.deltaBestLiftPct);
    item.avgDeltaBestPrecisionPct += number(row.deltaBestPrecisionPct);
    groups.set(key, item);
  }

  return Array.from(groups.values())
    .map((item) => ({
      ...item,
      avgDeltaBestLiftPct: round(item.avgDeltaBestLiftPct / item.count),
      avgDeltaBestPrecisionPct: round(item.avgDeltaBestPrecisionPct / item.count)
    }))
    .sort((left, right) =>
      left.scope.localeCompare(right.scope) ||
      left.regimeLabel.localeCompare(right.regimeLabel) ||
      left.decision.localeCompare(right.decision)
    );
}

const validationOptions = parseValidationArgs(process.argv.slice(2));
const cleanPayload = await readJson(inputPath);
const macroPayload = await readJson(macroPath);
const technical = validateDecisionTrees(cleanPayload, config, validationOptions);
const macro = validateDecisionTrees(cleanPayload, config, {
  ...validationOptions,
  macroRows: macroPayload.rows || []
});
const holdoutComparison = compareRows(technical.holdoutRows, macro.holdoutRows);
const regimeComparison = compareRows(technical.regimeRows, macro.regimeRows);
const comparisonRows = [
  ...holdoutComparison,
  ...regimeComparison
];
const summaryRows = summarizeComparison(comparisonRows);

await writeJson(comparisonJsonPath, {
  metadata: {
    instrument: cleanPayload.metadata.instrument,
    bar: cleanPayload.metadata.bar,
    trainTo: validationOptions.trainTo,
    validateFrom: validationOptions.validateFrom,
    validateTo: validationOptions.validateTo || technical.metadata.validateTo,
    generatedAt: new Date().toISOString(),
    macroRows: macroPayload.rows?.length || 0
  },
  summaryRows,
  comparisonRows
});
await writeCsv(comparisonCsvPath, comparisonRows);
await writeCsv(summaryCsvPath, summaryRows);

console.log(JSON.stringify({
  step: "compare-macro-impact",
  inputPath,
  macroPath,
  comparisonJsonPath,
  comparisonCsvPath,
  summaryCsvPath,
  summaryRows,
  keepMacro: comparisonRows.filter((row) => row.decision === KEEP_MACRO).slice(0, 20),
  doNotKeepMacro: comparisonRows.filter((row) => row.decision === DROP_MACRO).slice(0, 20)
}, null, 2));
