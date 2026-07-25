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
    caches.open(CACHE).then((cache) => {
      // Cache the digest at install too, best-effort and separate from the
      // shell: on a first visit the app's own digest fetch runs before this
      // worker controls the page, so without this an install-then-offline
      // user would have no digest to fall back to. A missing digest.json
      // must not abort the install, hence the detached, catch-guarded add.
      cache.add("digest.json").catch(() => {});
      return cache.addAll(SHELL);
    }).then(() => self.skipWaiting())
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
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Cache-first for the shell: instant open.
  event.respondWith(
    caches.match(event.request).then((hit) => hit || fetch(event.request))
  );
});
