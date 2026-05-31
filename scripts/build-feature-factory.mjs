import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs, reportStem } from "../backtest/config.mjs";
import { buildFeatureFactory } from "../backtest/feature-factory.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const stem = fileStem(config);
const reportName = reportStem(config);
const inputPath = join(root, "data", "clean", `${stem}_clean.json`);
const featureJsonPath = join(root, "reports", `${reportName}_feature_factory.json`);
const featureCsvPath = join(root, "reports", `${reportName}_feature_factory_rows.csv`);

const cleanPayload = await readJson(inputPath);
const result = buildFeatureFactory(cleanPayload, config);

await writeJson(featureJsonPath, {
  metadata: result.metadata,
  features: result.features,
  featureStats: result.featureStats,
  current: result.current
});
await writeCsv(featureCsvPath, result.featureRows);

console.log(JSON.stringify({
  step: "build-feature-factory",
  inputPath,
  featureJsonPath,
  featureCsvPath,
  metadata: result.metadata,
  current: result.current
}, null, 2));
