import { access, readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { defaultConfig, fileStem, parseArgs, reportStem } from "../backtest/config.mjs";
import { buildDecisionJournal, decisionJournalIndexRow } from "../backtest/decision-journal.mjs";
import { readJson, writeCsv, writeJson } from "../backtest/io.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const config = parseArgs(process.argv.slice(2), defaultConfig);
const stem = fileStem(config);
const reportName = reportStem(config);
const inputPath = join(root, "data", "clean", `${stem}_clean.json`);
const journalDir = join(root, "reports", "decision-journal");
const indexJsonPath = join(journalDir, `${reportName}_decision_index.json`);
const indexCsvPath = join(journalDir, `${reportName}_decision_index.csv`);

function parseJournalArgs(argv) {
  const input = {
    decision: "观察",
    bias: "中性",
    confidence: 50,
    notes: "",
    tags: []
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const value = argv[index + 1];

    if (arg === "--decision" && value) {
      input.decision = value;
      index += 1;
    } else if (arg === "--bias" && value) {
      input.bias = value;
      index += 1;
    } else if (arg === "--confidence" && value) {
      input.confidence = Number(value);
      index += 1;
    } else if (arg === "--notes" && value) {
      input.notes = value;
      index += 1;
    } else if (arg === "--tags" && value) {
      input.tags = value.split(",").map((item) => item.trim()).filter(Boolean);
      index += 1;
    }
  }

  return input;
}

async function readJsonIfExists(filePath, fallback) {
  try {
    await access(filePath);
    return JSON.parse(await readFile(filePath, "utf8"));
  } catch {
    return fallback;
  }
}

const cleanPayload = await readJson(inputPath);
const result = buildDecisionJournal(cleanPayload, config, parseJournalArgs(process.argv.slice(2)));
const journalPath = join(journalDir, `${result.journal.id}_decision.json`);
const indexRow = decisionJournalIndexRow(result.journal);
const existingIndex = await readJsonIfExists(indexJsonPath, []);
const nextIndex = [
  ...existingIndex.filter((row) => row.id !== indexRow.id),
  indexRow
].sort((left, right) => `${left.date}_${left.createdAt}`.localeCompare(`${right.date}_${right.createdAt}`));

await writeJson(journalPath, result.journal);
await writeJson(indexJsonPath, nextIndex);
await writeCsv(indexCsvPath, nextIndex);

console.log(JSON.stringify({
  step: "create-decision-journal",
  inputPath,
  journalPath,
  indexJsonPath,
  indexCsvPath,
  market: result.journal.market,
  weather: {
    name: result.journal.weather.name,
    confidencePct: result.journal.weather.confidencePct
  },
  neuralState: result.journal.neuralState && {
    stateCode: result.journal.neuralState.stateCode,
    name: result.journal.neuralState.name,
    confidence: result.journal.neuralState.confidence
  },
  router: {
    topRoutes: result.journal.router.topRoutes.slice(0, 3),
    currentSignals: result.journal.router.currentSignals.slice(0, 5)
  },
  human: result.journal.human
}, null, 2));
