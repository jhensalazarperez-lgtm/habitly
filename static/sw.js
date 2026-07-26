const CACHE_NAME = "habitly-v4";

// Only cache things that never change per-user: pure static assets.
// Auth pages (login/signup/logout) are intentionally NOT cached, since
// caching them caused stale-page issues around login/logout transitions.
const STATIC_ASSETS = [
  "/static/style.css",
  "/static/auth.css",
  "/static/app.js",
  "/static/manifest.json"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // API calls -> always try network first (data must be fresh), fall back
  // to cache only if genuinely offline.
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Auth flow pages and the personalized main app page must always be
  // fresh from the server, never served from cache. We deliberately do
  // NOT call respondWith() for these at all - if we re-fetch them
  // ourselves and that fetch() rejects (e.g. Render's free-tier server
  // waking up from sleep, which can take up to ~50s), Chrome shows a
  // hard "ERR_FAILED" instead of its normal loading/retry behavior. Not
  // calling respondWith() lets the browser handle the request exactly
  // as if there were no service worker involved at all.
  const alwaysNetwork = ["/", "/login", "/signup", "/logout"];
  if (alwaysNetwork.includes(url.pathname) || url.pathname.startsWith("/uploads/")) {
    return;
  }

  // Static assets (CSS/JS/manifest) -> NETWORK FIRST, cache only as an
  // offline fallback. Cache-first was causing deployed CSS/JS updates to
  // never actually reach the browser, since the very first cached copy
  // would be served forever regardless of what changed on the server.
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
