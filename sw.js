// Offline copies of every page, so a game added to the Home Screen still opens
// without a connection. scripts/build_pwa.py publishes this with VERSION,
// PAGES and MUSIC filled in; a new VERSION on each deploy refreshes every copy.
//
// Pages come from the network first, so a deploy shows up straight away, and
// from the offline copy when the network fails or is too slow to answer. The
// music games play (music/*.mid) is kept with them and comes from the offline
// copy first: it only changes along with VERSION. Google Fonts are kept too.
// Everything else (the leaderboard, War's rooms, Sentry, Counterscale) goes
// straight to the network untouched.

const VERSION = 'dev';
const PAGES = [];
const MUSIC = [];

const PAGE_CACHE = `pages-${VERSION}`;
const FONT_CACHE = 'fonts';
const FONT_HOSTS = ['fonts.googleapis.com', 'fonts.gstatic.com'];
// How long to wait for the network before falling back to the offline copy.
const NETWORK_WAIT_MS = 4000;

addEventListener('install', (event) => {
  event.waitUntil(precache().then(() => skipWaiting()));
});

addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name.startsWith('pages-') && name !== PAGE_CACHE) await caches.delete(name);
    }
    await clients.claim();
  })());
});

addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin === location.origin) {
    const page = pagePath(url.pathname);
    if (PAGES.includes(page)) event.respondWith(networkFirst(event, page));
    else if (MUSIC.includes(url.pathname)) event.respondWith(keptFirst(event, url.pathname));
  } else if (FONT_HOSTS.includes(url.hostname)) {
    event.respondWith(fromFontCache(event));
  }
});

// Every page and piece of music or none: if one can't be fetched, installing
// fails and the previous version keeps serving its copies until the next try.
async function precache() {
  const responses = await Promise.all([...PAGES, ...MUSIC].map(async (page) => {
    const response = await fetch(page, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`${page}: ${response.status}`);
    return [page, response];
  }));
  const cache = await caches.open(PAGE_CACHE);
  await Promise.all(responses.map(([page, response]) => cache.put(page, unredirected(response))));
}

// /war, /war.html and /war?room=ABCD are all the War page; /index.html is /.
function pagePath(pathname) {
  return pathname.replace(/\.html$/, '').replace(/\/index$/, '/') || '/';
}

// Safari refuses to show a page from a response that followed a redirect.
function unredirected(response) {
  if (!response.redirected) return response;
  const { status, statusText, headers } = response;
  return new Response(response.body, { status, statusText, headers });
}

async function networkFirst(event, page) {
  const network = fetch(event.request).then((response) => {
    if (response.ok && response.type === 'basic') {
      const copy = unredirected(response.clone());
      event.waitUntil(caches.open(PAGE_CACHE).then((cache) => cache.put(page, copy)));
    }
    return response;
  });
  // Keep the worker alive to save the copy even if the offline one answers first.
  event.waitUntil(network.catch(() => {}));

  const cached = await (await caches.open(PAGE_CACHE)).match(page);
  if (!cached) return network;
  const fallback = network.then((response) => (response.status >= 500 ? cached : response), () => cached);
  const slow = new Promise((resolve) => setTimeout(resolve, NETWORK_WAIT_MS, cached));
  return Promise.race([fallback, slow]);
}

async function keptFirst(event, path) {
  const cached = await (await caches.open(PAGE_CACHE)).match(path);
  return cached || fetch(event.request);
}

// Font files never change at a given URL, so a kept one is simply used. The
// stylesheets that list them rarely change, so a kept one is used straight
// away and refreshed behind it.
async function fromFontCache(event) {
  const cache = await caches.open(FONT_CACHE);
  const cached = await cache.match(event.request);
  if (cached && new URL(event.request.url).hostname === 'fonts.gstatic.com') return cached;
  const network = fetch(event.request).then((response) => {
    // Stylesheets come back opaque, since the page asks for them without CORS.
    if (response.ok || response.type === 'opaque') {
      const copy = response.clone();
      event.waitUntil(cache.put(event.request, copy));
    }
    return response;
  });
  if (!cached) return network;
  event.waitUntil(network.catch(() => {}));
  return cached;
}
