const CACHE = "boosterbox-v9";
const SHELL = ["./", "index.html", "style.css", "app.js", "manifest.webmanifest", "favicon.svg", "icon-192.png", "icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)));
  self.skipWaiting();
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  // Always-fresh data — bypass the shell cache and only fall back to it
  // if the network is offline. Both snapshot AND history are dynamic.
  if (url.pathname.endsWith("/data/snapshot.json")
      || url.pathname.endsWith("/data/sales_history.json")) {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
  } else {
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
  }
});
