"use strict";

// Bump this string whenever shell files change, to retire the old cache.
const CACHE = "signal-v1";

const SHELL = [
  ".",
  "index.html",
  "style.css",
  "app.js",
  "readout.js",
  "manifest.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      // Both are awaited (Promise.all) so install does not finish until the
      // digest is cached too — on a first visit the app's own digest fetch
      // runs before this worker controls the page, so without this an
      // install-then-offline user would have no digest to fall back to.
      // The digest add is catch-guarded so a missing digest.json still cannot
      // abort the install.
      Promise.all([
        cache.add("digest.json").catch(() => {}),
        cache.addAll(SHELL),
      ])
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  const isDigest = new URL(event.request.url).pathname.endsWith("digest.json");

  if (isDigest) {
    // Network-first: today's digest if reachable, yesterday's if not.
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          // A 404/500 still resolves fetch. Treat it as a miss so a bad
          // response never overwrites (poisons) the last-good cached digest,
          // and the app falls back to the good copy instead of an error page.
          if (!response.ok) throw new Error("bad digest status " + response.status);
          const copy = response.clone();
          // Await the cache write before returning, so the copy is durably
          // stored (not a detached, racy write).
          return caches.open(CACHE)
            .then((cache) => cache.put(event.request, copy))
            .then(() => response);
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Cache-first for the shell: instant open. The shell is fully precached, so
  // a cache hit is expected; the network fallback covers assets not in SHELL
  // (e.g. user-supplied fonts), which simply fail offline and degrade via the
  // CSS fallback stack — an acceptable, non-breaking outcome.
  event.respondWith(
    caches.match(event.request).then((hit) => hit || fetch(event.request))
  );
});
