// Page views through Counterscale (https://counterscale.dev), which runs on
// our own Cloudflare account. The build inlines this into every page: each
// game, the home page and the colophon. tests/test_analytics.py covers it.
//
// Each page view sends the page's path, never its query string or
// fragment, and the site the visitor came from, as its origin only.
// Counterscale adds the browser and device from the user agent and the
// country Cloudflare works out from the IP address, which it doesn't keep.
// It sets no cookies.
(() => {
  // Counterscale's address: its custom domain, made by OpenTofu in
  // mwarkentin/infra (worker_domains.tf). While it's empty, nothing loads
  // and nothing is sent.
  const COUNTERSCALE_URL = 'https://stats.michaelwarkentin.com';
  const SITE_ID = 'games';
  // Counterscale's own tracker, checked against this hash before it runs.
  const TRACKER = {
    src: 'https://cdn.jsdelivr.net/npm/@counterscale/tracker@3.4.1/dist/module/index.js',
    integrity: 'sha384-TrbROGVCq2iQjt2unBGc1J1F/aWAilTeZsXPOGEeCswrzsk2oi6fkFfAJAEfLBOr',
  };

  // Local previews and the tests report nothing.
  if (!COUNTERSCALE_URL || location.hostname !== 'games.michaelwarkentin.com') return;

  // Another site's origin, or this one's, which the tracker records as no
  // referrer. Passing one stops the tracker looking for a referrer in this
  // page's own query string (?ref=, ?source= and the like).
  const referrer = (() => {
    try {
      const { origin } = new URL(document.referrer);
      return origin === 'null' ? location.origin : origin;
    } catch {
      return location.origin;
    }
  })();

  // import() can't check an integrity hash, so fetch the module, which the
  // browser checks, and import that.
  fetch(TRACKER.src, { integrity: TRACKER.integrity })
    .then((response) => (response.ok ? response.text() : Promise.reject(new Error(response.statusText))))
    .then((code) => {
      const url = URL.createObjectURL(new Blob([code], { type: 'text/javascript' }));
      return import(url).finally(() => URL.revokeObjectURL(url));
    })
    .then((Counterscale) => {
      // The games are separate pages, so one page view per load; the tracker
      // won't watch history.pushState.
      Counterscale.init({ siteId: SITE_ID, reporterUrl: `${COUNTERSCALE_URL}/collect`, autoTrackPageviews: false });
      Counterscale.trackPageview({ url: location.pathname, referrer });
    })
    // A blocked or failed tracker costs a page view, never the game.
    .catch(() => {});
})();
