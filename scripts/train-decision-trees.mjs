import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs, reportStem } from "../backtest/config.mjs";
import { trainDecisionTreeSuite } from "../backtest/decision-tree-suite.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const stem = fileStem(config);
const reportName = reportStem(config);
const inputPath = join(root, "data", "clean", `${stem}_clean.json`);
const modelPath = join(root, "reports", `${reportName}_decision_tree_suite.json`);
const currentCsvPath = join(root, "reports", `${reportName}_decision_tree_current.csv`);
const rulesCsvPath = join(root, "reports", `${reportName}_decision_tree_rules.csv`);
const qualityCsvPath = join(root, "reports", `${reportName}_decision_tree_quality_audit.csv`);
const importanceCsvPath = join(root, "reports", `${reportName}_decision_tree_importance.csv`);
const macroPath = join(root, "data", "macro", `${stem}_macro_features.json`);

function hasFlag(argv, flag) {
  return argv.includes(flag);
}

async function readMacroRowsIfRequested(argv) {
  if (!hasFlag(argv, "--macro")) return [];
  const payload = await readJson(macroPath);
  return payload.rows || [];
}

const cleanPayload = await readJson(inputPath);
const macroRows = await readMacroRowsIfRequested(process.argv.slice(2));
const result = trainDecisionTreeSuite(cleanPayload, config, { macroRows });

await writeJson(modelPath, {
  metadata: result.metadata,
  current: result.current,
  stateTree: result.stateTree,
  volatilityTrees: result.volatilityTrees,
  strategyTrees: result.strategyTrees,
  qualityRows: result.qualityRows
});
await writeCsv(currentCsvPath, result.currentRows);
await writeCsv(rulesCsvPath, result.ruleRows);
await writeCsv(qualityCsvPath, result.qualityRows);
await writeCsv(importanceCsvPath, result.importanceRows);

console.log(JSON.stringify({
  step: "train-decision-trees",
  inputPath,
  modelPath,
  currentCsvPath,
  rulesCsvPath,
  qualityCsvPath,
  importanceCsvPath,
  macroEnabled: result.metadata.macroEnabled,
  metadata: result.metadata,
  current: result.current
}, null, 2));
