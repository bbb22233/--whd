import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs, reportStem } from "../backtest/config.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";
import { runPositionStateBacktest } from "../backtest/position-state.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const stem = fileStem(config);
const reportName = reportStem(config);
const inputPath = join(root, "data", "clean", `${stem}_clean.json`);
const summaryJsonPath = join(root, "reports", `${reportName}_position_state_summary.json`);
const summaryCsvPath = join(root, "reports", `${reportName}_position_state_summary.csv`);
const observationsCsvPath = join(root, "reports", `${reportName}_position_state_observations.csv`);

const cleanPayload = await readJson(inputPath);
const result = runPositionStateBacktest(cleanPayload, config);

await writeJson(summaryJsonPath, {
  metadata: result.metadata,
  summaryRows: result.summaryRows
});
await writeCsv(summaryCsvPath, result.summaryRows);
await writeCsv(observationsCsvPath, result.observationRows);

console.log(JSON.stringify({
  step: "backtest-position-state",
  inputPath,
  summaryJsonPath,
  summaryCsvPath,
  observationsCsvPath,
  metadata: result.metadata
}, null, 2));
