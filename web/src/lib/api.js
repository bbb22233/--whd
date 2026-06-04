// 数据层:复用现有 REST 契约(/api/dashboard/current 主路 + 静态 reports 回退)。
// API_BASE 可插拔:默认走同源(dev 由 vite proxy 转 8000;生产由反代同源)。
// 本地直连场景设 window.__API_BASE__ = "http://127.0.0.1:8000"。
const API_BASE =
  typeof window !== "undefined" && typeof window.__API_BASE__ === "string"
    ? window.__API_BASE__
    : "";

export const DEFAULT_INSTRUMENT = "BTC-USDT";
export const DEFAULT_BAR = "1D";
export const SUPPORTED_BARS = ["1D", "4H", "8H", "1W"];
const SYMBOL_RE = /^[A-Z0-9]+-[A-Z0-9]+$/;

export const DEFAULT_SYMBOLS = [
  "BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT", "DOGE-USDT", "ADA-USDT",
  "LINK-USDT", "AVAX-USDT", "TON-USDT", "TRX-USDT", "DOT-USDT", "BCH-USDT", "LTC-USDT",
];

export function normalizeInstrument(value) {
  if (!value) return null;
  let s = String(value).trim().toUpperCase().replaceAll("_", "-").replaceAll("/", "-");
  if (!s) return null;
  if (!s.includes("-")) s = `${s}-USDT`;
  return SYMBOL_RE.test(s) ? s : null;
}

export function normalizeBar(value) {
  if (!value) return null;
  const b = String(value).trim().toUpperCase();
  if (b === "1") return "1D";
  return SUPPORTED_BARS.includes(b) ? b : null;
}

const prefix = (inst, bar) => `${inst.replaceAll("-", "_")}_${bar}`;

function buildPaths(instrument, bar) {
  const p = prefix(instrument, bar);
  const ei = encodeURIComponent(instrument);
  const eb = encodeURIComponent(bar);
  const report = (name) => ({
    primary: `${API_BASE}/api/reports/${name}`,
    fallback: `${API_BASE}/reports/${name}`,
  });
  return {
    dashboard: `${API_BASE}/api/dashboard/current?instrument=${ei}&bar=${eb}`,
    weather: report(`${p}_market_weather_router.json`),
    features: report(`${p}_feature_factory.json`),
    deviations: report(`${p}_deviation_rules.json`),
    candles: { primary: `${API_BASE}/api/candles/${ei}/${eb}`, fallback: `${API_BASE}/data/clean/${p}_clean.json` },
  };
}

async function fetchJson(source, optional = false) {
  const candidates = typeof source === "string" ? [source] : [source.primary, source.fallback].filter(Boolean);
  let lastError = null;
  for (const path of candidates) {
    try {
      const res = await fetch(path, { cache: "no-store" });
      if (!res.ok) throw new Error(`${path} ${res.status}`);
      return await res.json();
    } catch (err) {
      lastError = err;
    }
  }
  if (optional) return null;
  throw lastError ?? new Error("no data source");
}

async function fetchLegacy(paths) {
  const [weather, features, deviations, candles] = await Promise.all([
    fetchJson(paths.weather),
    fetchJson(paths.features),
    fetchJson(paths.deviations, true),
    fetchJson(paths.candles, true),
  ]);
  return { weather, features, deviations, candles, sourceMode: "legacy_files" };
}

export async function fetchDashboard(instrument, bar) {
  const paths = buildPaths(instrument, bar);
  try {
    const payload = await fetchJson(paths.dashboard);
    return {
      weather: payload.weather,
      features: payload.features,
      deviations: payload.deviations,
      candles: payload.candles,
      sources: payload.sources,
      sourceMode: "dashboard_api",
    };
  } catch (err) {
    return fetchLegacy(paths);
  }
}

export async function fetchSymbols() {
  try {
    const res = await fetch(`${API_BASE}/api/market/symbols`, { cache: "no-store" });
    if (!res.ok) throw new Error(String(res.status));
    const data = await res.json();
    const syms = Array.isArray(data?.symbols) ? data.symbols : [];
    const norm = Array.from(new Set(syms.map(normalizeInstrument).filter(Boolean)));
    return norm.length ? norm : DEFAULT_SYMBOLS;
  } catch {
    return DEFAULT_SYMBOLS;
  }
}
