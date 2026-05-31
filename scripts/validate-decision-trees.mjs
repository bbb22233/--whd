import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs, reportStem } from "../backtest/config.mjs";
import { validateDecisionTrees } from "../backtest/decision-tree-validation.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const stem = fileStem(config);
const reportName = reportStem(config);
const inputPath = join(root, "data", "clean", `${stem}_clean.json`);
const validationJsonPath = join(root, "reports", `${reportName}_decision_tree_validation.json`);
const holdoutCsvPath = join(root, "reports", `${reportName}_decision_tree_holdout_validation.csv`);
const regimeCsvPath = join(root, "reports", `${reportName}_decision_tree_macro_regime_validation.csv`);
const predictionsCsvPath = join(root, "reports", `${reportName}_decision_tree_validation_predictions.csv`);
const macroPath = join(root, "data", "macro", `${stem}_macro_features.json`);

function hasFlag(argv, flag) {
  return argv.includes(flag);
}

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

async function readMacroRowsIfRequested(argv) {
  if (!hasFlag(argv, "--macro")) return [];
  const payload = await readJson(macroPath);
  return payload.rows || [];
}

const cleanPayload = await readJson(inputPath);
const argv = process.argv.slice(2);
const result = validateDecisionTrees(cleanPayload, config, {
  ...parseValidationArgs(argv),
  macroRows: await readMacroRowsIfRequested(argv)
});

await writeJson(validationJsonPath, {
  metadata: result.metadata,
  holdoutRows: result.holdoutRows,
  regimeRows: result.regimeRows
});
await writeCsv(holdoutCsvPath, result.holdoutRows);
await writeCsv(regimeCsvPath, result.regimeRows);
await writeCsv(predictionsCsvPath, result.predictionRows);

console.log(JSON.stringify({
  step: "validate-decision-trees",
  inputPath,
  validationJsonPath,
  holdoutCsvPath,
  regimeCsvPath,
  predictionsCsvPath,
  macroEnabled: result.metadata.macroEnabled,
  metadata: result.metadata,
  holdoutRows: result.holdoutRows.filter((row) => row.validationQuality !== "弱参考").slice(0, 20),
  regimeRows: result.regimeRows.filter((row) => row.validationQuality !== "弱参考").slice(0, 20)
}, null, 2));
