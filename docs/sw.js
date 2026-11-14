// PoliDesk service worker: lets the briefing open without a connection.
// Page and data: try the network first, fall back to the last saved copy.
// Fonts are served by the site itself and come from the cache.
const CACHE = 'polidesk-v2';
const SHELL = ['./', 'index.html', 'favicon.svg', 'icon-192.png', 'manifest.webmanifest', 'edition.json', 'fonts/inter.woff', 'fonts/source-serif-4.woff'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Strip the ?t= cache-buster so every fetch of edition.json shares one cache entry.
const keyOf = (url) => { const u = new URL(url); u.search = ''; return u.href; };

async function networkFirst(req) {
  const cache = await caches.open(CACHE);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(keyOf(req.url), res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(keyOf(req.url)) || (req.mode === 'navigate' && await cache.match('./'));
    if (hit) return hit;
    throw err;
  }
}

async function staleWhileRevalidate(req) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(req);
  const fresh = fetch(req).then((res) => { if (res.ok || res.type === 'opaque') cache.put(req, res.clone()); return res; }).catch(() => hit);
  return hit || fresh;
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin === self.location.origin) { e.respondWith(url.pathname.startsWith('/fonts/') ? staleWhileRevalidate(req) : networkFirst(req)); return; }
  // News photos come from many sites; let the browser handle them normally.
});
