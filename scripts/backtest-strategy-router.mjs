import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs, reportStem } from "../backtest/config.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";
import { runStrategyRouterBacktest } from "../backtest/strategy-router-backtest.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const stem = fileStem(config);
const reportName = reportStem(config);
const inputPath = join(root, "data", "clean", `${stem}_clean.json`);
const summaryJsonPath = join(root, "reports", `${reportName}_strategy_router_summary.json`);
const summaryCsvPath = join(root, "reports", `${reportName}_strategy_router_summary.csv`);
const observationsCsvPath = join(root, "reports", `${reportName}_strategy_router_observations.csv`);

const cleanPayload = await readJson(inputPath);
const result = runStrategyRouterBacktest(cleanPayload, config);

await writeJson(summaryJsonPath, {
  metadata: result.metadata,
  summaryRows: result.summaryRows
});
await writeCsv(summaryCsvPath, result.summaryRows);
await writeCsv(observationsCsvPath, result.observationRows);

console.log(JSON.stringify({
  step: "backtest-strategy-router",
  inputPath,
  summaryJsonPath,
  summaryCsvPath,
  observationsCsvPath,
  metadata: result.metadata
}, null, 2));
