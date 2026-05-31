import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defaultConfig, fileStem, parseArgs } from "../backtest/config.mjs";
import {
  buildMacroFeatureRows,
  fredSources,
  macroRowsToCsvRows,
  parseFredCsv,
  parseStablecoinChart,
  stablecoinSource
} from "../backtest/macro-data.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const stem = fileStem(config);
const rawDir = join(root, "data", "macro", "raw");
const macroJsonPath = join(root, "data", "macro", `${stem}_macro_features.json`);
const macroCsvPath = join(root, "data", "macro", `${stem}_macro_features.csv`);
const cleanPath = join(root, "data", "clean", `${stem}_clean.json`);

async function fetchText(url) {
  const response = await fetch(url, {
    headers: {
      "user-agent": "quant-monitor-terminal/0.1"
    }
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status} ${response.statusText}: ${url}`);
  }

  return response.text();
}

async function downloadFredSources() {
  await mkdir(rawDir, { recursive: true });
  const sourceRowsByKey = {};

  for (const source of fredSources) {
    const text = await fetchText(source.url);
    await writeFile(join(rawDir, `${source.id}.csv`), text, "utf8");
    sourceRowsByKey[source.key] = parseFredCsv(text, source);
  }

  return sourceRowsByKey;
}

async function downloadStablecoinSource() {
  try {
    const text = await fetchText(stablecoinSource.url);
    await writeFile(join(rawDir, "defillama_stablecoincharts_all.json"), text, "utf8");
    return parseStablecoinChart(JSON.parse(text));
  } catch (error) {
    console.warn(`stablecoin source skipped: ${error.message}`);
    return [];
  }
}

const cleanPayload = await readJson(cleanPath);
const sourceRowsByKey = await downloadFredSources();
const stablecoinRows = await downloadStablecoinSource();
if (stablecoinRows.length) {
  sourceRowsByKey.stablecoinSupply = stablecoinRows;
}

const candleDates = cleanPayload.candles.map((candle) => candle.date);
const macroRows = buildMacroFeatureRows(candleDates, sourceRowsByKey);

await writeJson(macroJsonPath, {
  metadata: {
    instrument: cleanPayload.metadata.instrument,
    bar: cleanPayload.metadata.bar,
    firstDate: macroRows[0]?.date || null,
    lastDate: macroRows.at(-1)?.date || null,
    rowCount: macroRows.length,
    sources: [
      ...fredSources.map((source) => ({
        key: source.key,
        id: source.id,
        label: source.label,
        url: source.url
      })),
      {
        key: stablecoinSource.key,
        label: stablecoinSource.label,
        url: stablecoinSource.url,
        rows: stablecoinRows.length
      }
    ],
    generatedAt: new Date().toISOString()
  },
  rows: macroRows
});
await writeCsv(macroCsvPath, macroRowsToCsvRows(macroRows));

console.log(JSON.stringify({
  step: "download-macro-data",
  cleanPath,
  rawDir,
  macroJsonPath,
  macroCsvPath,
  rowCount: macroRows.length,
  stablecoinRows: stablecoinRows.length
}, null, 2));
