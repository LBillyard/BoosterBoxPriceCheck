const DATA_URL = "data/snapshot.json";
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
    const r = await fetch(DATA_URL, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    render(await r.json());
  } catch (e) {
    errEl.textContent = `Could not load data: ${e.message}`;
    errEl.hidden = false;
  } finally {
    setTimeout(() => refreshBtn.classList.remove("spin"), 500);
  }
}

function render(snap) {
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

  const liVal = document.getElementById("stat-listings-value");
  const liSub = document.getElementById("stat-listings-sub");
  if (snap.listings && snap.listings.length) {
    const min = Math.min(...snap.listings.map(l => l.gbp));
    liVal.textContent = String(snap.listings.length);
    liSub.textContent = `from ${fmtGBP.format(min)}`;
  } else {
    liVal.textContent = "0";
    liSub.textContent = "none active";
  }

  renderListings(snap);
  renderRecentSales(snap);
}

function sourcePillClass(source) {
  const known = ["ebay_us", "ebay_uk", "130point", "pricecharting"];
  return "feed-pill s-" + (known.includes(source) ? source : "default");
}
function sourceLabel(source) {
  const map = { ebay_us: "eBay US", ebay_uk: "eBay UK", "130point": "130point", pricecharting: "PriceCharting" };
  return map[source] || source;
}

function makeFeedItem({ source, title, gbp, usd, date, url }) {
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
  const titleEl = document.createElement("span");
  titleEl.className = "feed-title";
  const t = title || "";
  titleEl.textContent = t.length > 60 ? t.slice(0, 59).trimEnd() + "…" : t;
  titleEl.title = t;
  top.append(pill, titleEl);
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

function renderRecentSales(snap) {
  const card = document.getElementById("recent-sales-card");
  const list = document.getElementById("recent-sales-list");
  const count = document.getElementById("feed-count");
  list.innerHTML = "";
  const sales = (snap.recent_sales || []).slice(0, 10);
  if (!sales.length) { card.hidden = true; return; }
  card.hidden = false;
  count.textContent = `${snap.recent_sales.length} total`;
  for (const s of sales) {
    list.appendChild(makeFeedItem({
      source: s.source,
      title: s.title,
      gbp: s.gbp,
      usd: s.usd,
      date: s.date,
      url: s.url,
    }));
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
