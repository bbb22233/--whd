import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs, reportStem } from "../backtest/config.mjs";
import { runIndicatorBacktest } from "../backtest/indicator-backtest.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const stem = fileStem(config);
const reportName = reportStem(config);
const inputPath = join(root, "data", "clean", `${stem}_clean.json`);
const summaryJsonPath = join(root, "reports", `${reportName}_indicator_bucket_summary.json`);
const summaryCsvPath = join(root, "reports", `${reportName}_indicator_bucket_summary.csv`);
const contrastCsvPath = join(root, "reports", `${reportName}_indicator_extreme_contrast.csv`);
const observationsCsvPath = join(root, "reports", `${reportName}_indicator_observations.csv`);

const cleanPayload = await readJson(inputPath);
const result = runIndicatorBacktest(cleanPayload, config);

await writeJson(summaryJsonPath, {
  metadata: result.metadata,
  summaryRows: result.summaryRows,
  contrastRows: result.contrastRows
});
await writeCsv(summaryCsvPath, result.summaryRows);
await writeCsv(contrastCsvPath, result.contrastRows);
await writeCsv(observationsCsvPath, result.observationRows);

console.log(JSON.stringify({
  step: "backtest-indicators",
  inputPath,
  summaryJsonPath,
  summaryCsvPath,
  contrastCsvPath,
  observationsCsvPath,
  metadata: result.metadata
}, null, 2));
