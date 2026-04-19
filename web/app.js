const DATA_URL = "data/snapshot.json";
const HISTORY_URL = "data/sales_history.json";
const POLL_MS = 5 * 60 * 1000;

const fmtGBP = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
const fmtGBPexact = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 2 });
const fmtUSD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const fmtGBPSigned = new Intl.NumberFormat("en-GB", {
  style: "currency", currency: "GBP", maximumFractionDigits: 0, signDisplay: "exceptZero",
});

function relative(iso) {
  const t = new Date(iso).getTime();
  const diffMin = Math.round((Date.now() - t) / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const h = Math.round(diffMin / 60);
  if (h < 48) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

function setStatus(ageHrs) {
  const dot = document.getElementById("status-dot");
  if (ageHrs > 24) {
    dot.classList.remove("dot-live");
    dot.classList.add("dot-stale");
  } else {
    dot.classList.add("dot-live");
    dot.classList.remove("dot-stale");
  }
}

function animateNumber(el, target, formatter, durationMs = 700) {
  const start = parseFloat(el.dataset.value || "0");
  const startTime = performance.now();
  function step(now) {
    const t = Math.min(1, (now - startTime) / durationMs);
    const eased = 1 - Math.pow(1 - t, 3);
    const current = start + (target - start) * eased;
    el.textContent = formatter(current);
    if (t < 1) requestAnimationFrame(step);
    else el.dataset.value = String(target);
  }
  requestAnimationFrame(step);
}

async function load() {
  const errEl = document.getElementById("error");
  const refreshBtn = document.getElementById("refresh");
  errEl.hidden = true;
  refreshBtn.classList.add("spin");
  try {
    // History is best-effort — the file may not exist yet on a fresh
    // deploy. Snapshot is required.
    const [snapRes, histRes] = await Promise.all([
      fetch(DATA_URL, { cache: "no-store" }),
      fetch(HISTORY_URL, { cache: "no-store" }).catch(() => null),
    ]);
    if (!snapRes.ok) throw new Error(`HTTP ${snapRes.status}`);
    const snap = await snapRes.json();
    let history = [];
    if (histRes && histRes.ok) {
      try { history = await histRes.json(); } catch { history = []; }
      if (!Array.isArray(history)) history = [];
    }
    render(snap, history);
  } catch (e) {
    errEl.textContent = `Could not load data: ${e.message}`;
    errEl.hidden = false;
  } finally {
    setTimeout(() => refreshBtn.classList.remove("spin"), 500);
  }
}

function render(snap, history) {
  history = history || [];
  const updatedEl = document.getElementById("updated");
  const ageHrs = (Date.now() - new Date(snap.scraped_at).getTime()) / 3_600_000;
  updatedEl.textContent = `Updated ${relative(snap.scraped_at)}`;
  setStatus(ageHrs);

  // ─── Hero ────────────────────────────────────────────────────────
  const hero = snap.prices.loose || snap.prices.new || snap.prices.sealed
            || (snap.prices && Object.values(snap.prices)[0]);
  if (hero) {
    animateNumber(document.getElementById("hero-gbp"), hero.gbp, v => fmtGBP.format(Math.round(v)));
    document.getElementById("hero-usd").textContent = fmtUSD.format(hero.usd);
  }

  const plRow = document.getElementById("pl-row");
  const plBadge = document.getElementById("pl-badge");
  if (snap.purchase_price_gbp && hero) {
    const delta = hero.gbp - snap.purchase_price_gbp;
    const pct = (delta / snap.purchase_price_gbp) * 100;
    const arrow = delta >= 0 ? "▲" : "▼";
    plBadge.textContent = `${arrow} ${fmtGBPSigned.format(delta)} (${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%)`;
    plBadge.className = "pl-pill " + (delta >= 0 ? "up" : "down");
    plRow.hidden = false;
  } else {
    plRow.hidden = true;
  }

  // ─── Stats grid ──────────────────────────────────────────────────
  if (hero) {
    document.getElementById("stat-loose-value").textContent = fmtGBP.format(hero.gbp);
    document.getElementById("stat-loose-sub").textContent = fmtUSD.format(hero.usd);
  }

  const lsVal = document.getElementById("stat-last-sold-value");
  const lsSub = document.getElementById("stat-last-sold-sub");
  if (snap.last_sold) {
    lsVal.textContent = fmtGBP.format(snap.last_sold.gbp);
    lsSub.textContent = snap.last_sold.date;
  } else {
    lsVal.textContent = "—";
    lsSub.textContent = "no record";
  }

  // Prefer eBay active listings for the "Active listings" stat — they're
  // the actual currently-for-sale supply. Fall back to PriceCharting's
  // marketplace array if eBay returned nothing.
  const liVal = document.getElementById("stat-listings-value");
  const liSub = document.getElementById("stat-listings-sub");
  const activeForStat = (snap.active_listings && snap.active_listings.length)
                       ? snap.active_listings
                       : (snap.listings || []);
  if (activeForStat.length) {
    const min = Math.min(...activeForStat.map(l => l.gbp));
    liVal.textContent = String(activeForStat.length);
    liSub.textContent = `from ${fmtGBP.format(min)}`;
  } else {
    liVal.textContent = "0";
    liSub.textContent = "none active";
  }

  renderActive(snap);
  renderListings(snap);
  renderRecentSales(snap, history);
  renderSparkline(history);
  renderSources(snap);
}

function sourcePillClass(source) {
  const known = ["ebay_us", "ebay_uk", "130point", "pricecharting"];
  return "feed-pill s-" + (known.includes(source) ? source : "default");
}
function sourceLabel(source) {
  const map = { ebay_us: "eBay US", ebay_uk: "eBay UK", "130point": "130point", pricecharting: "PriceCharting" };
  return map[source] || source;
}

// One-glance scam check: a small pill rendered next to the source pill on
// each eBay listing. Tier thresholds match the brief — <10 = very new
// (almost always a scam in the £20k+ band), 10–99 = low (proceed with
// caution), >=100 = established. Returns null when feedback is unknown so
// callers can decide whether to render an UNKNOWN grey pill or skip.
// Compact integer formatter: 109500 -> "109K", 1500000 -> "1.5M".
// Keeps the trust pill narrow so it never pushes the title off-screen.
function _compactFb(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1).replace(/\.0$/, "") + "M";
  if (n >= 1_000)     return (n / 1_000).toFixed(n >= 10_000 ? 0 : 1).replace(/\.0$/, "") + "K";
  return String(n);
}

function trustPill(feedback) {
  if (feedback === null || feedback === undefined) return null;
  let cls, label;
  if (feedback < 10)        { cls = "trust-new";    label = `${feedback} fb`; }
  else if (feedback < 100)  { cls = "trust-low";    label = `${feedback} fb`; }
  else                      { cls = "trust-ok";     label = `${_compactFb(feedback)}+ fb`; }
  const span = document.createElement('span');
  span.className = `trust-pill ${cls}`;
  span.textContent = label;
  span.title = `${feedback.toLocaleString()} eBay feedback`;
  return span;
}

function unknownTrustPill() {
  const span = document.createElement('span');
  span.className = 'trust-pill trust-unknown';
  span.textContent = '? fb';
  span.title = 'Seller feedback unknown';
  return span;
}

function makeFeedItem({ source, title, gbp, usd, date, url, sellerFeedback, sellerName, sellerPositivePct }) {
  const li = document.createElement("li");
  const wrap = url ? document.createElement("a") : document.createElement("div");
  if (url) {
    wrap.href = url;
    wrap.target = "_blank";
    wrap.rel = "noopener";
  } else {
    wrap.className = "feed-row";
  }

  const left = document.createElement("div");
  left.className = "feed-l";
  const top = document.createElement("div");
  top.className = "feed-l-top";
  const pill = document.createElement("span");
  pill.className = sourcePillClass(source);
  pill.textContent = sourceLabel(source);

  // Trust pill: only meaningful for eBay sources (the only feeds where we
  // have seller-feedback data). PriceCharting / 130point pass undefined and
  // get no pill at all to avoid visual noise.
  const isEbay = source === "ebay_us" || source === "ebay_uk";
  let trust = null;
  if (isEbay) {
    trust = trustPill(sellerFeedback);
    if (!trust) trust = unknownTrustPill();
    if (sellerName) {
      const pctTxt = (sellerPositivePct !== null && sellerPositivePct !== undefined)
        ? ` · ${sellerPositivePct}% positive` : "";
      trust.title = `${sellerName} · ${sellerFeedback ?? "?"} feedback${pctTxt}`;
    }
  }

  const titleEl = document.createElement("span");
  titleEl.className = "feed-title";
  const t = title || "";
  titleEl.textContent = t.length > 60 ? t.slice(0, 59).trimEnd() + "…" : t;
  titleEl.title = t;
  if (trust) top.append(pill, trust, titleEl);
  else top.append(pill, titleEl);
  const bot = document.createElement("div");
  bot.className = "feed-l-bot";
  bot.textContent = date || "";
  left.append(top, bot);

  const right = document.createElement("div");
  right.className = "feed-r";
  const gbpEl = document.createElement("div");
  gbpEl.className = "feed-gbp";
  gbpEl.textContent = fmtGBP.format(gbp);
  const usdEl = document.createElement("div");
  usdEl.className = "feed-usd";
  usdEl.textContent = fmtUSD.format(usd);
  right.append(gbpEl, usdEl);

  wrap.append(left, right);
  li.appendChild(wrap);
  return li;
}

function renderRecentSales(snap, history) {
  const card = document.getElementById("recent-sales-card");
  const list = document.getElementById("recent-sales-list");
  const count = document.getElementById("feed-count");
  list.innerHTML = "";
  // Prefer the cumulative history file; fall back to the latest snapshot
  // window when history is empty (fresh deploy, no scrape yet).
  const source = (history && history.length)
                ? history
                : (snap.recent_sales || []);
  const sales = source.slice(0, 15);
  if (!sales.length) { card.hidden = true; return; }
  card.hidden = false;
  count.textContent = `${source.length} total`;
  for (const s of sales) {
    list.appendChild(makeFeedItem({
      source: s.source,
      title: s.title,
      gbp: s.gbp,
      usd: s.usd,
      date: s.date,
      url: s.url,
      sellerName: s.seller_name,
      sellerFeedback: s.seller_feedback,
      sellerPositivePct: s.seller_positive_pct,
    }));
  }
}

function renderActive(snap) {
  const card = document.getElementById("active-card");
  const list = document.getElementById("active-list");
  const count = document.getElementById("active-count");
  const empty = document.getElementById("active-empty");
  list.innerHTML = "";
  const items = snap.active_listings || [];
  card.hidden = false;
  if (!items.length) {
    count.textContent = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  count.textContent = `${items.length} live · from ${fmtGBP.format(Math.min(...items.map(l => l.gbp)))}`;
  for (const item of items) {
    list.appendChild(makeFeedItem({
      source: item.source,
      title: item.title,
      gbp: item.gbp,
      usd: item.usd,
      date: null,
      url: item.url,
      sellerName: item.seller_name,
      sellerFeedback: item.seller_feedback,
      sellerPositivePct: item.seller_positive_pct,
    }));
  }
}

function renderSources(snap) {
  const row = document.getElementById("sources-row");
  const list = document.getElementById("sources-list");
  const counts = snap.source_counts || {};
  list.innerHTML = "";
  const order = ["pricecharting", "ebay_us", "ebay_uk", "130point", "ebay_us_active", "ebay_uk_active"];
  // Always show PriceCharting (it gave us the hero/last-sold data) at 1.
  const pcCount = (snap.prices && Object.keys(snap.prices).length) || 0;
  const all = { pricecharting: pcCount, ...counts };
  const keys = order.filter(k => k in all);

  if (!keys.length) { row.hidden = true; return; }
  row.hidden = false;
  for (const k of keys) {
    const n = all[k];
    const li = document.createElement("li");
    const chip = document.createElement("span");
    chip.className = "source-chip";
    const dot = document.createElement("span");
    dot.className = "src-dot " + (n > 0 ? "ok" : "empty");
    const name = document.createElement("span");
    name.className = "src-name";
    name.textContent = sourceLabel(k.replace(/_active$/, "")) + (k.endsWith("_active") ? " (live)" : "");
    const cnt = document.createElement("span");
    cnt.className = "src-count " + (n > 0 ? "nonzero" : "zero");
    cnt.textContent = String(n);
    chip.append(dot, name, cnt);
    li.appendChild(chip);
    list.appendChild(li);
  }
}

function renderListings(snap) {
  const card = document.getElementById("listings-card");
  const list = document.getElementById("listings-list");
  list.innerHTML = "";
  if (!snap.listings || !snap.listings.length) { card.hidden = true; return; }
  card.hidden = false;
  for (const item of snap.listings) {
    list.appendChild(makeFeedItem({
      source: "pricecharting",
      title: item.condition,
      gbp: item.gbp,
      usd: item.usd,
      date: null,
      url: item.url,
    }));
  }
}

function renderSparkline(history) {
  const svg = document.getElementById("hero-spark");
  if (!svg) return;
  // Take last ~20 dated entries, ascending by date.
  const dated = (history || [])
    .filter(h => h.date && Number.isFinite(h.usd))
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
    .slice(-20);
  if (dated.length < 2) { svg.hidden = true; return; }

  const W = 200, H = 28, pad = 1;
  const xs = dated.map((_, i) => i);
  const ys = dated.map(d => d.usd);
  const xMin = 0, xMax = xs.length - 1;
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const ySpan = yMax - yMin || 1;
  const sx = i => pad + (i - xMin) / (xMax - xMin || 1) * (W - 2 * pad);
  const sy = v => H - pad - (v - yMin) / ySpan * (H - 2 * pad);
  const points = dated.map((d, i) => `${sx(i).toFixed(2)},${sy(d.usd).toFixed(2)}`);
  const linePath = `M ${points.join(" L ")}`;
  const areaPath = `${linePath} L ${sx(xMax).toFixed(2)},${(H - pad).toFixed(2)} L ${sx(0).toFixed(2)},${(H - pad).toFixed(2)} Z`;

  svg.innerHTML = `
    <defs>
      <linearGradient id="spark-fill" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" stop-color="#4ade80" stop-opacity="0.28"/>
        <stop offset="100%" stop-color="#4ade80" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <path d="${areaPath}" fill="url(#spark-fill)" stroke="none"/>
    <path d="${linePath}" fill="none" stroke="#4ade80"
          stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"
          opacity="0.85"/>
  `;
  svg.hidden = false;
}

document.getElementById("refresh").addEventListener("click", load);
load();
setInterval(load, POLL_MS);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

let wakeLock = null;
let wakeLockUnavailable = false;
async function requestWakeLock() {
  if (!("wakeLock" in navigator) || wakeLockUnavailable) return;
  try {
    wakeLock = await navigator.wakeLock.request("screen");
  } catch (e) {
    wakeLockUnavailable = true;  // don't retry on every visibility change
  }
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") requestWakeLock();
});
requestWakeLock();
