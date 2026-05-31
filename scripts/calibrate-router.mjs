import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs, reportStem } from "../backtest/config.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";
import { runRouterCalibration } from "../backtest/router-calibrator.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const stem = fileStem(config);
const reportName = reportStem(config);
const inputPath = join(root, "data", "clean", `${stem}_clean.json`);
const calibrationJsonPath = join(root, "reports", `${reportName}_router_calibration.json`);
const calibrationCsvPath = join(root, "reports", `${reportName}_router_calibration.csv`);
const currentCsvPath = join(root, "reports", `${reportName}_router_current_signals.csv`);

const cleanPayload = await readJson(inputPath);
const result = runRouterCalibration(cleanPayload, config);

await writeJson(calibrationJsonPath, {
  metadata: result.metadata,
  calibrationRows: result.calibrationRows
});
await writeCsv(calibrationCsvPath, result.calibrationRows);
await writeCsv(currentCsvPath, result.metadata.currentSignals);

console.log(JSON.stringify({
  step: "calibrate-router",
  inputPath,
  calibrationJsonPath,
  calibrationCsvPath,
  currentCsvPath,
  metadata: result.metadata
}, null, 2));
