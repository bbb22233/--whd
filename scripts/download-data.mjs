import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs } from "../backtest/config.mjs";
import { downloadOkxHistory } from "../backtest/okx.mjs";
import { writeJson } from "../backtest/io.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const outputPath = join(root, "data", "raw", `${fileStem(config)}_raw.json`);

const rawPayload = await downloadOkxHistory(config);
await writeJson(outputPath, rawPayload);

console.log(JSON.stringify({
  step: "download",
  outputPath,
  instrument: rawPayload.instrument,
  bar: rawPayload.bar,
  rowCount: rawPayload.rowCount,
  pageCount: rawPayload.pageCount,
  downloadedAt: rawPayload.downloadedAt
}, null, 2));
