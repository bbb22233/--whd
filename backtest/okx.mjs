const OKX_HISTORY_CANDLES_URL = "https://www.okx.com/api/v5/market/history-candles";

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function rowTimestamp(row) {
  return Number(row?.[0]);
}

export async function downloadOkxHistory(config) {
  const startedAt = new Date();
  const startMs = startedAt.getTime() - (config.days * 24 * 60 * 60 * 1000);
  const rowsByTime = new Map();
  let cursor = null;
  let page = 0;
  let lastOldest = Infinity;

  while (page < 80) {
    const url = new URL(OKX_HISTORY_CANDLES_URL);
    url.searchParams.set("instId", config.instrument);
    url.searchParams.set("bar", config.bar);
    url.searchParams.set("limit", String(config.requestLimit));
    if (cursor) url.searchParams.set("after", cursor);

    const response = await fetch(url.toString(), { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`OKX request failed: ${response.status} ${response.statusText}`);
    }

    const payload = await response.json();
    if (payload.code !== "0" || !Array.isArray(payload.data)) {
      throw new Error(`OKX response unavailable: ${payload.msg || payload.code || "unknown"}`);
    }

    const pageRows = payload.data.filter((row) => Number.isFinite(rowTimestamp(row)));
    if (!pageRows.length) break;

    for (const row of pageRows) {
      rowsByTime.set(String(rowTimestamp(row)), row);
    }

    const oldest = Math.min(...pageRows.map(rowTimestamp));
    page += 1;

    if (oldest <= startMs || oldest >= lastOldest) break;
    lastOldest = oldest;
    cursor = String(oldest);
    await sleep(140);
  }

  const rows = Array.from(rowsByTime.values())
    .sort((left, right) => rowTimestamp(left) - rowTimestamp(right))
    .filter((row) => rowTimestamp(row) >= startMs);

  return {
    source: "OKX",
    endpoint: OKX_HISTORY_CANDLES_URL,
    instrument: config.instrument,
    bar: config.bar,
    requestedDays: config.days,
    downloadedAt: new Date().toISOString(),
    pageCount: page,
    rowCount: rows.length,
    rows
  };
}
