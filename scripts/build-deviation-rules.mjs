import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs, reportStem } from "../backtest/config.mjs";
import { runDeviationStudy } from "../backtest/deviation-study.mjs";
import { buildDeviationRules } from "../backtest/deviation-rules.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const stem = fileStem(config);
const reportName = reportStem(config);
const inputPath = join(root, "data", "clean", `${stem}_clean.json`);
const outputJsonPath = join(root, "reports", `${reportName}_deviation_rules.json`);
const currentCsvPath = join(root, "reports", `${reportName}_deviation_rules_current.csv`);
const libraryCsvPath = join(root, "reports", `${reportName}_deviation_rule_library.csv`);

const cleanPayload = await readJson(inputPath);
const study = runDeviationStudy(cleanPayload, config);
const rules = buildDeviationRules(study);

await writeJson(outputJsonPath, rules);
await writeCsv(currentCsvPath, rules.currentRuleRows);
await writeCsv(libraryCsvPath, rules.ruleLibraryRows);

console.log(JSON.stringify({
  step: "build-deviation-rules",
  inputPath,
  outputJsonPath,
  currentCsvPath,
  libraryCsvPath,
  metadata: rules.metadata,
  finalWeather: rules.finalWeather
}, null, 2));
