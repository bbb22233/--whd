import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs } from "../backtest/config.mjs";
import { candlesToCsvRows, cleanOkxRaw } from "../backtest/clean.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const stem = fileStem(config);
const inputPath = join(root, "data", "raw", `${stem}_raw.json`);
const cleanJsonPath = join(root, "data", "clean", `${stem}_clean.json`);
const cleanCsvPath = join(root, "data", "clean", `${stem}_clean.csv`);

const rawPayload = await readJson(inputPath);
const cleanPayload = cleanOkxRaw(rawPayload);

await writeJson(cleanJsonPath, cleanPayload);
await writeCsv(cleanCsvPath, candlesToCsvRows(cleanPayload.candles));

console.log(JSON.stringify({
  step: "clean",
  inputPath,
  cleanJsonPath,
  cleanCsvPath,
  metadata: cleanPayload.metadata
}, null, 2));
