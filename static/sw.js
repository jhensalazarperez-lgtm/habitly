const CACHE_NAME = "habitly-v1";

// Only cache things that are safe to reuse for anyone: public auth pages
// and static assets. We deliberately do NOT cache "/" (the main app page)
// since it's personalized per logged-in user and behind auth.
const STATIC_ASSETS = [
  "/static/style.css",
  "/static/auth.css",
  "/static/app.js",
  "/static/manifest.json",
  "/login",
  "/signup"
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

  // Never cache the personalized main app page or uploaded photos -
  // always go to network for these.
  if (url.pathname === "/" || url.pathname.startsWith("/uploads/")) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Everything else (static assets, auth pages) -> cache first.
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
