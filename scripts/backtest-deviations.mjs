import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs, reportStem } from "../backtest/config.mjs";
import { runDeviationStudy } from "../backtest/deviation-study.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const stem = fileStem(config);
const reportName = reportStem(config);
const inputPath = join(root, "data", "clean", `${stem}_clean.json`);
const summaryJsonPath = join(root, "reports", `${reportName}_deviation_study.json`);
const currentCsvPath = join(root, "reports", `${reportName}_deviation_current.csv`);
const stateSummaryCsvPath = join(root, "reports", `${reportName}_deviation_state_summary.csv`);
const metricSummaryCsvPath = join(root, "reports", `${reportName}_deviation_metric_summary.csv`);
const metricContrastCsvPath = join(root, "reports", `${reportName}_deviation_metric_contrast.csv`);
const stateObservationsCsvPath = join(root, "reports", `${reportName}_deviation_state_observations.csv`);
const metricObservationsCsvPath = join(root, "reports", `${reportName}_deviation_metric_observations.csv`);

const cleanPayload = await readJson(inputPath);
const result = runDeviationStudy(cleanPayload, config);

await writeJson(summaryJsonPath, {
  metadata: result.metadata,
  currentRows: result.currentRows,
  stateSummaryRows: result.stateSummaryRows,
  metricSummaryRows: result.metricSummaryRows,
  metricContrastRows: result.metricContrastRows
});
await writeCsv(currentCsvPath, result.currentRows);
await writeCsv(stateSummaryCsvPath, result.stateSummaryRows);
await writeCsv(metricSummaryCsvPath, result.metricSummaryRows);
await writeCsv(metricContrastCsvPath, result.metricContrastRows);
await writeCsv(stateObservationsCsvPath, result.stateObservationRows);
await writeCsv(metricObservationsCsvPath, result.metricObservationRows);

console.log(JSON.stringify({
  step: "backtest-deviations",
  inputPath,
  summaryJsonPath,
  currentCsvPath,
  stateSummaryCsvPath,
  metricSummaryCsvPath,
  metricContrastCsvPath,
  stateObservationsCsvPath,
  metricObservationsCsvPath,
  metadata: result.metadata,
  currentRows: result.currentRows
}, null, 2));
