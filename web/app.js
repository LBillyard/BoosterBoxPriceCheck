const DATA_URL = "data/snapshot.json";
const POLL_MS = 5 * 60 * 1000;

const fmtGBP = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
const fmtUSD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const fmtGBPSigned = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0, signDisplay: "exceptZero" });

function relative(iso) {
  const t = new Date(iso).getTime();
  const diffMin = Math.round((Date.now() - t) / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const h = Math.round(diffMin / 60);
  if (h < 48) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
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
    setTimeout(() => refreshBtn.classList.remove("spin"), 400);
  }
}

function render(snap) {
  const updatedEl = document.getElementById("updated");
  const ageHrs = (Date.now() - new Date(snap.scraped_at).getTime()) / 3_600_000;
  updatedEl.textContent = `Updated ${relative(snap.scraped_at)}`;
  updatedEl.classList.toggle("stale", ageHrs > 24);

  const hero = snap.prices.loose || snap.prices.new || snap.prices.sealed || Object.values(snap.prices)[0];
  document.getElementById("hero-gbp").textContent = fmtGBP.format(hero.gbp);
  document.getElementById("hero-usd").textContent = fmtUSD.format(hero.usd);

  const plRow = document.getElementById("pl-row");
  const plBadge = document.getElementById("pl-badge");
  if (snap.purchase_price_gbp && hero.gbp) {
    const delta = hero.gbp - snap.purchase_price_gbp;
    const pct = (delta / snap.purchase_price_gbp) * 100;
    plBadge.textContent = `${fmtGBPSigned.format(delta)} (${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%)`;
    plBadge.className = "badge rounded-pill " + (delta >= 0 ? "text-bg-success" : "text-bg-danger");
    plRow.classList.remove("d-none");
  } else {
    plRow.classList.add("d-none");
  }

  const cEl = document.getElementById("conditions");
  cEl.innerHTML = "";
  const entries = Object.entries(snap.prices);
  const colClass = entries.length === 1 ? "col-12" : entries.length === 2 ? "col-6" : "col-4";
  for (const [label, vals] of entries) {
    const col = document.createElement("div");
    col.className = colClass;
    const card = document.createElement("div");
    card.className = "condition-card";
    const lab = document.createElement("div");
    lab.className = "cond-label";
    lab.textContent = label;
    const val = document.createElement("div");
    val.className = "cond-value";
    val.textContent = fmtGBP.format(vals.gbp);
    card.append(lab, val);
    col.appendChild(card);
    cEl.appendChild(col);
  }

  const lsEl = document.getElementById("last-sold");
  const lsSub = document.getElementById("last-sold-sub");
  if (snap.last_sold) {
    lsEl.textContent = fmtGBP.format(snap.last_sold.gbp);
    lsSub.textContent = `${fmtUSD.format(snap.last_sold.usd)} · ${snap.last_sold.date}`;
  } else {
    lsEl.textContent = "—";
    lsSub.textContent = "No recorded sales";
  }

  const sumEl = document.getElementById("listings-summary");
  const sumSub = document.getElementById("listings-sub");
  const card = document.getElementById("listings-card");
  const list = document.getElementById("listings-list");
  list.innerHTML = "";
  if (snap.listings && snap.listings.length) {
    const min = Math.min(...snap.listings.map(l => l.gbp));
    sumEl.textContent = `${snap.listings.length} active`;
    sumSub.textContent = `from ${fmtGBP.format(min)}`;
    card.hidden = false;
    for (const item of snap.listings) {
      const li = document.createElement("li");
      li.className = "list-group-item border-0 listing-row";
      const cond = document.createElement("span");
      cond.className = "listing-cond";
      cond.textContent = item.condition;
      const gbp = document.createElement("span");
      gbp.className = "listing-gbp";
      gbp.textContent = fmtGBP.format(item.gbp);
      const usd = document.createElement("span");
      usd.className = "listing-usd";
      usd.textContent = fmtUSD.format(item.usd);
      if (item.url) {
        const a = document.createElement("a");
        a.href = item.url;
        a.target = "_blank";
        a.rel = "noopener";
        a.className = "text-decoration-none text-reset d-flex align-items-center gap-2 w-100";
        a.append(cond, gbp, usd);
        li.appendChild(a);
      } else {
        li.append(cond, gbp, usd);
      }
      list.appendChild(li);
    }
  } else {
    sumEl.textContent = "0";
    sumSub.textContent = "No active listings";
    card.hidden = true;
  }
}

document.getElementById("refresh").addEventListener("click", load);
load();
setInterval(load, POLL_MS);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

let wakeLock = null;
async function requestWakeLock() {
  if (!("wakeLock" in navigator)) return;
  try {
    wakeLock = await navigator.wakeLock.request("screen");
  } catch (e) {
    console.warn("wake lock denied:", e);
  }
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") requestWakeLock();
});
requestWakeLock();
