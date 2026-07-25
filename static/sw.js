const CACHE_NAME = "habitly-v2";

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
  // fresh from the server, never served from cache - these involve
  // session state (login/logout/signup) that a cached response would
  // get wrong.
  const alwaysNetwork = ["/", "/login", "/signup", "/logout"];
  if (alwaysNetwork.includes(url.pathname) || url.pathname.startsWith("/uploads/")) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Everything else (plain static assets like CSS/JS/manifest) -> cache first.
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
