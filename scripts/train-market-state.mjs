import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs, reportStem } from "../backtest/config.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";
import { trainMarketStateModel } from "../backtest/market-state.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const stem = fileStem(config);
const reportName = reportStem(config);
const inputPath = join(root, "data", "clean", `${stem}_clean.json`);
const modelPath = join(root, "reports", `${reportName}_state_model.json`);
const statesCsvPath = join(root, "reports", `${reportName}_state_summary.csv`);
const assignmentsCsvPath = join(root, "reports", `${reportName}_state_assignments.csv`);
const stateStrategyCsvPath = join(root, "reports", `${reportName}_state_strategy_profile.csv`);
const decisionRulesCsvPath = join(root, "reports", `${reportName}_state_decision_rules.csv`);
const decisionImportanceCsvPath = join(root, "reports", `${reportName}_state_decision_importance.csv`);

const cleanPayload = await readJson(inputPath);
const result = trainMarketStateModel(cleanPayload, config);

await writeJson(modelPath, {
  metadata: result.metadata,
  features: result.features,
  featureStats: result.featureStats,
  decisionTree: result.decisionTree,
  states: result.states,
  currentState: result.currentState
});
await writeCsv(statesCsvPath, result.stateRows);
await writeCsv(assignmentsCsvPath, result.assignmentRows);
await writeCsv(stateStrategyCsvPath, result.stateStrategyRows);
await writeCsv(decisionRulesCsvPath, result.decisionRuleRows);
await writeCsv(decisionImportanceCsvPath, result.decisionImportanceRows);

console.log(JSON.stringify({
  step: "train-market-state",
  inputPath,
  modelPath,
  statesCsvPath,
  assignmentsCsvPath,
  stateStrategyCsvPath,
  decisionRulesCsvPath,
  decisionImportanceCsvPath,
  metadata: result.metadata,
  currentState: result.currentState
}, null, 2));
