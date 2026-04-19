const DATA_URL = "data/snapshot.json";
const POLL_MS = 5 * 60 * 1000;

const fmtGBP = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
const fmtUSD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

function relative(iso) {
  const t = new Date(iso).getTime();
  const diffMin = Math.round((Date.now() - t) / 60000);
  if (diffMin < 60) return `${diffMin}m ago`;
  const h = Math.round(diffMin / 60);
  if (h < 48) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

async function load() {
  const errEl = document.getElementById("error");
  errEl.hidden = true;
  try {
    const r = await fetch(DATA_URL, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    render(await r.json());
  } catch (e) {
    errEl.textContent = `Could not load data: ${e.message}`;
    errEl.hidden = false;
  }
}

function render(snap) {
  const updatedEl = document.getElementById("updated");
  const ageHrs = (Date.now() - new Date(snap.scraped_at).getTime()) / 3_600_000;
  updatedEl.textContent = `Updated ${relative(snap.scraped_at)}`;
  if (ageHrs > 24) updatedEl.classList.add("stale");

  const hero = snap.prices.loose || snap.prices.new || snap.prices.sealed || Object.values(snap.prices)[0];
  document.getElementById("hero-gbp").textContent = fmtGBP.format(hero.gbp);
  document.getElementById("hero-usd").textContent = fmtUSD.format(hero.usd);

  const cEl = document.getElementById("conditions");
  cEl.innerHTML = "";
  for (const [label, vals] of Object.entries(snap.prices)) {
    const div = document.createElement("div");
    div.className = "condition";
    div.innerHTML = `<div class="label">${label}</div><div class="value">${fmtGBP.format(vals.gbp)}</div>`;
    cEl.appendChild(div);
  }

  const lsEl = document.getElementById("last-sold");
  if (snap.last_sold) {
    lsEl.textContent = `${fmtGBP.format(snap.last_sold.gbp)} · ${snap.last_sold.date}`;
  } else {
    lsEl.textContent = "No recorded sales";
  }

  const sumEl = document.getElementById("listings-summary");
  const list = document.getElementById("listings-list");
  list.innerHTML = "";
  if (snap.listings && snap.listings.length) {
    const min = Math.min(...snap.listings.map(l => l.gbp));
    sumEl.textContent = `${snap.listings.length} listed · from ${fmtGBP.format(min)}`;
    for (const item of snap.listings) {
      const li = document.createElement("li");
      li.innerHTML = `
        <span class="cond">${item.condition}</span>
        <span class="gbp">${fmtGBP.format(item.gbp)}</span>
        <span class="usd">${fmtUSD.format(item.usd)}</span>`;
      list.appendChild(li);
    }
  } else {
    sumEl.textContent = "No active listings";
  }
}

document.getElementById("refresh").addEventListener("click", load);
load();
setInterval(load, POLL_MS);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

// Keep screen awake while the app is visible (PWA only).
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
