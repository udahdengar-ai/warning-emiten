// Ambil dari internet dulu (data selalu terbaru); kalau offline, pakai salinan terakhir.
const C = "we-v1";
self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET" || new URL(e.request.url).origin !== location.origin) return;
  e.respondWith(fetch(e.request).then(r => {
    const salin = r.clone(); const kunci = e.request.url.split("?")[0];
    caches.open(C).then(c => c.put(kunci, salin)); return r;
  }).catch(() => caches.match(e.request.url.split("?")[0])));
});
