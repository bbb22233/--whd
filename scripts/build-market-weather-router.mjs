import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs, reportStem } from "../backtest/config.mjs";
import { buildMarketWeatherRouter } from "../backtest/market-weather-router.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const stem = fileStem(config);
const reportName = reportStem(config);
const inputPath = join(root, "data", "clean", `${stem}_clean.json`);
const outputJsonPath = join(root, "reports", `${reportName}_market_weather_router.json`);
const currentCsvPath = join(root, "reports", `${reportName}_market_weather_current.csv`);
const scoresCsvPath = join(root, "reports", `${reportName}_market_weather_scores.csv`);
const componentsCsvPath = join(root, "reports", `${reportName}_market_weather_components_current.csv`);
const summaryCsvPath = join(root, "reports", `${reportName}_market_weather_component_summary.csv`);
const observationsCsvPath = join(root, "reports", `${reportName}_market_weather_observations.csv`);

const cleanPayload = await readJson(inputPath);
const result = buildMarketWeatherRouter(cleanPayload, config);

await writeJson(outputJsonPath, {
  metadata: result.metadata,
  current: result.current,
  strategyScores: result.strategyScores,
  deviationFinalWeather: result.deviationFinalWeather,
  currentComponentRows: result.currentComponentRows,
  componentSummaryRows: result.componentSummaryRows
});
await writeCsv(currentCsvPath, result.current ? [result.current] : []);
await writeCsv(scoresCsvPath, result.strategyScores);
await writeCsv(componentsCsvPath, result.currentComponentRows);
await writeCsv(summaryCsvPath, result.componentSummaryRows);
await writeCsv(observationsCsvPath, result.observationRows);

console.log(JSON.stringify({
  step: "build-market-weather-router",
  inputPath,
  outputJsonPath,
  currentCsvPath,
  scoresCsvPath,
  componentsCsvPath,
  summaryCsvPath,
  observationsCsvPath,
  metadata: result.metadata,
  current: result.current,
  strategyScores: result.strategyScores,
  deviationFinalWeather: result.deviationFinalWeather
}, null, 2));
