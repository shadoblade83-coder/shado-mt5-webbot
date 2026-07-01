const CACHE = "shado-mt5-webbot-v1";
const ASSETS = ["./", "./index.html", "./styles.css", "./app.js", "./manifest.json", "./icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.protocol.startsWith("http") && !url.hostname.includes("127.0.0.1") && !url.hostname.includes("localhost")) {
    event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
  }
});
