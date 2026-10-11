// Caches the app shell so the page opens without a network.
const CACHE = "signsaathi-v1";
const SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icons/icon.svg"];
self.addEventListener("install", e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL))));
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))));
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  if (new URL(e.request.url).pathname.includes("/api/")) return; // never cache API responses
  e.respondWith(fetch(e.request).then(r => { const c = r.clone(); caches.open(CACHE).then(x => x.put(e.request, c)); return r; }).catch(() => caches.match(e.request)));
});
