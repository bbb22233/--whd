const OKX_HISTORY_CANDLES_URL = "https://www.okx.com/api/v5/market/history-candles";
const DEFAULT_REQUEST_LIMIT = 100;
const DAY_MS = 24 * 60 * 60 * 1000;
const HOUR_MS = 60 * 60 * 1000;
const PAGE_SAFETY_MULTIPLIER = 1.2;
const PAGE_SAFETY_EXTRA = 3;
const RETRY_DELAYS_MS = [2000, 4000, 8000, 16000];

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function rowTimestamp(row) {
  return Number(row?.[0]);
}

function barToMs(bar) {
  const text = String(bar || "1D");
  const value = Number.parseInt(text, 10) || 1;

  if (text.endsWith("m")) return value * 60 * 1000;
  if (text.endsWith("H")) return value * HOUR_MS;
  if (text.endsWith("D")) return value * DAY_MS;
  if (text.endsWith("W")) return value * 7 * DAY_MS;
  return DAY_MS;
}

function calculateMaxPages(config) {
  const barMs = barToMs(config.bar);
  const requestLimit = Math.max(1, Math.floor(Number(config.requestLimit) || DEFAULT_REQUEST_LIMIT));
  const requestedBars = Math.ceil((config.days * DAY_MS) / barMs);

  return {
    requestLimit,
    maxPages: Math.max(1, Math.ceil((requestedBars / requestLimit) * PAGE_SAFETY_MULTIPLIER) + PAGE_SAFETY_EXTRA)
  };
}

function timestampToIso(timestamp) {
  return Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : null;
}

async function fetchOkxPage(url) {
  let lastError = null;

  for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt += 1) {
    try {
      const response = await fetch(url.toString(), { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`OKX request failed: ${response.status} ${response.statusText}`);
      }

      const payload = await response.json();
      if (payload.code !== "0" || !Array.isArray(payload.data)) {
        throw new Error(`OKX response unavailable: ${payload.msg || payload.code || "unknown"}`);
      }

      return {
        payload,
        retryCount: attempt
      };
    } catch (error) {
      lastError = error;
      if (attempt >= RETRY_DELAYS_MS.length) break;
      await sleep(RETRY_DELAYS_MS[attempt]);
    }
  }

  throw lastError;
}

export async function downloadOkxHistory(config) {
  const startedAt = new Date();
  const startMs = startedAt.getTime() - (config.days * 24 * 60 * 60 * 1000);
  const { requestLimit, maxPages } = calculateMaxPages(config);
  const rowsByTime = new Map();
  let cursor = null;
  let page = 0;
  let lastOldest = Infinity;
  let oldestReached = null;
  let retryCount = 0;

  while (page < maxPages) {
    const url = new URL(OKX_HISTORY_CANDLES_URL);
    url.searchParams.set("instId", config.instrument);
    url.searchParams.set("bar", config.bar);
    url.searchParams.set("limit", String(requestLimit));
    if (cursor) url.searchParams.set("after", cursor);

    const pageResult = await fetchOkxPage(url);
    retryCount += pageResult.retryCount;

    const pageRows = pageResult.payload.data.filter((row) => Number.isFinite(rowTimestamp(row)));
    if (!pageRows.length) break;

    for (const row of pageRows) {
      rowsByTime.set(String(rowTimestamp(row)), row);
    }

    const oldest = Math.min(...pageRows.map(rowTimestamp));
    oldestReached = oldestReached === null ? oldest : Math.min(oldestReached, oldest);
    page += 1;

    if (oldest <= startMs || oldest >= lastOldest) break;
    lastOldest = oldest;
    cursor = String(oldest);
    await sleep(140);
  }

  const rows = Array.from(rowsByTime.values())
    .sort((left, right) => rowTimestamp(left) - rowTimestamp(right))
    .filter((row) => rowTimestamp(row) >= startMs);
  const truncated = oldestReached === null || oldestReached > startMs;

  return {
    source: "OKX",
    endpoint: OKX_HISTORY_CANDLES_URL,
    instrument: config.instrument,
    bar: config.bar,
    requestedDays: config.days,
    requestedStartMs: startMs,
    requestedStartDate: timestampToIso(startMs),
    requestLimit,
    maxPages,
    downloadedAt: new Date().toISOString(),
    pageCount: page,
    rowCount: rows.length,
    retryCount,
    oldestReached,
    oldestReachedDate: timestampToIso(oldestReached),
    truncated,
    rows
  };
}
