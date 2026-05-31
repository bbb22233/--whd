const DAY_MS = 24 * 60 * 60 * 1000;
const HOUR_MS = 60 * 60 * 1000;

function finite(value) {
  return Number.isFinite(value);
}

export function barToMs(bar) {
  const text = String(bar || "1D");
  const value = Number.parseInt(text, 10) || 1;

  if (text.endsWith("m")) return value * 60 * 1000;
  if (text.endsWith("H")) return value * HOUR_MS;
  if (text.endsWith("D")) return value * DAY_MS;
  if (text.endsWith("W")) return value * 7 * DAY_MS;
  return DAY_MS;
}

export function formatCandleDate(openTime, bar) {
  const duration = barToMs(bar);
  const iso = new Date(openTime).toISOString();
  return duration < DAY_MS ? iso.slice(0, 16).replace("T", " ") : iso.slice(0, 10);
}

function normalizeRow(row, bar) {
  const openTime = Number(row[0]);
  const open = Number(row[1]);
  const high = Number(row[2]);
  const low = Number(row[3]);
  const close = Number(row[4]);
  const volume = Number(row[7] || row[5]);
  const confirm = row[8] === undefined ? "1" : String(row[8]);
  const duration = barToMs(bar);

  return {
    openTime,
    closeTime: openTime + duration - 1,
    date: formatCandleDate(openTime, bar),
    open,
    high,
    low,
    close,
    volume,
    confirm
  };
}

function isValidCandle(candle) {
  const highLowRatio = candle.low > 0 ? candle.high / candle.low : Infinity;
  const openCloseRatio = Math.max(candle.open, candle.close) / Math.min(candle.open, candle.close);

  return finite(candle.openTime) &&
    finite(candle.open) &&
    finite(candle.high) &&
    finite(candle.low) &&
    finite(candle.close) &&
    finite(candle.volume) &&
    candle.open > 0 &&
    candle.high > 0 &&
    candle.low > 0 &&
    candle.close > 0 &&
    candle.high >= Math.max(candle.open, candle.close) &&
    candle.low <= Math.min(candle.open, candle.close) &&
    highLowRatio <= 5 &&
    openCloseRatio <= 5;
}

export function cleanOkxRaw(rawPayload) {
  const seen = new Map();
  const invalidRows = [];
  let duplicateRows = 0;
  let unconfirmedRows = 0;
  const barMs = barToMs(rawPayload.bar);

  for (const row of rawPayload.rows || []) {
    const candle = normalizeRow(row, rawPayload.bar);

    if (candle.confirm !== "1") {
      unconfirmedRows += 1;
      continue;
    }

    if (!isValidCandle(candle)) {
      invalidRows.push(row);
      continue;
    }

    if (seen.has(candle.openTime)) duplicateRows += 1;
    seen.set(candle.openTime, candle);
  }

  const candles = Array.from(seen.values()).sort((left, right) => left.openTime - right.openTime);
  const missingBars = [];

  for (let index = 1; index < candles.length; index += 1) {
    const gap = candles[index].openTime - candles[index - 1].openTime;
    if (gap > barMs * 1.5) {
      missingBars.push({
        previousDate: candles[index - 1].date,
        nextDate: candles[index].date,
        missingBars: Math.round(gap / barMs) - 1
      });
    }
  }

  return {
    metadata: {
      source: rawPayload.source,
      instrument: rawPayload.instrument,
      bar: rawPayload.bar,
      requestedDays: rawPayload.requestedDays,
      downloadedAt: rawPayload.downloadedAt,
      cleanedAt: new Date().toISOString(),
      rawRows: rawPayload.rows?.length || 0,
      cleanRows: candles.length,
      duplicateRows,
      invalidRows: invalidRows.length,
      unconfirmedRows,
      missingBars,
      firstDate: candles[0]?.date || null,
      lastDate: candles.at(-1)?.date || null
    },
    candles
  };
}

export function candlesToCsvRows(candles) {
  return candles.map((candle) => ({
    date: candle.date,
    openTime: candle.openTime,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
    volume: candle.volume
  }));
}
