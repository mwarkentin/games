// Error reporting, performance and session replays through Sentry, inlined
// into every game's <head> by scripts/publish.py so it runs before the game.
// tests/test_telemetry.py covers it.
(() => {
  // The games project's DSN. While it's empty, nothing loads and nothing is sent.
  const SENTRY_DSN = 'https://8d55bf3ad202125a5bf149c37f672a10@o1142222.ingest.us.sentry.io/4512340849786880';
  const SDK = [
    {
      src: 'https://browser.sentry-cdn.com/11.10.0/bundle.tracing.replay.min.js',
      integrity: 'sha384-lQjzZ9F8GMovuCkjuP9IfDB/640c2hJYHmoc7LXfsG/Lhp9d05tRhrS4sfkOw/Hz',
    },
    {
      src: 'https://browser.sentry-cdn.com/11.10.0/replay-canvas.min.js',
      integrity: 'sha384-Eofzqse3XIpD8AmTdA8nBgYILVIBxqGSU6fUhSF1yaQlMfwCM29FmIl1mqrRwMIE',
    },
  ];

  // Local previews and the tests report nothing.
  if (!SENTRY_DSN || location.hostname !== 'games.michaelwarkentin.com') return;

  const release = document.currentScript?.dataset.release || undefined;
  // Everything is labelled with the game's name (funnels-and-buckets for
  // /funnels-and-buckets), so one game's issues, replays, traces and alerts
  // can be picked out.
  const game = location.pathname.split('/').pop().replace(/\.html$/, '');

  // Errors from before the SDK arrives are kept and sent once it does. If it
  // never does (a script blocked, or failing its integrity check), they're
  // let go, and no more are kept.
  // Errors from cross-origin scripts arrive as "Script error." with no error
  // attached; Sentry ignores those too.
  const early = [];
  const keep = (event) => {
    if (event.error || 'reason' in event) early.push(event.error ?? event.reason);
  };
  addEventListener('error', keep);
  addEventListener('unhandledrejection', keep);
  const stopKeeping = () => {
    removeEventListener('error', keep);
    removeEventListener('unhandledrejection', keep);
  };

  // How much each page load sends. Every page load's trace and one session in
  // ten's replay, while the site is quiet enough for that to be worth having;
  // a replay of a session with an error is always kept, since that's what an
  // error is no use without. For a busy day (a link on a news site's front
  // page), turn TRACES and REPLAYS down before it, so it can't use up a
  // month's quota in an hour (see "The knobs" in worker/VIRAL.md). Errors
  // are capped either way: no more than ERRORS_PER_PAGE from one page load,
  // and no more than SAME_ERROR_PER_PAGE of any one message, so one bug that
  // throws every frame can't. Sentry's own spike protection comes on top of
  // this, account-wide.
  const TRACES = 1;
  const REPLAYS = 0.1;
  const ERRORS_PER_PAGE = 25;
  const SAME_ERROR_PER_PAGE = 3;
  let sent = 0;
  const seen = new Map();
  const beforeSend = (event) => {
    const value = event.exception?.values?.[0];
    const key = value ? `${value.type}: ${value.value}` : event.message ?? '';
    const n = (seen.get(key) ?? 0) + 1;
    seen.set(key, n);
    if (n > SAME_ERROR_PER_PAGE || sent >= ERRORS_PER_PAGE) return null;
    sent++;
    return event;
  };

  const init = () => {
    stopKeeping();
    // The add-on can arrive without the bundle it adds to.
    if (typeof window.Sentry?.init !== 'function') return;
    Sentry.init({
      dsn: SENTRY_DSN,
      release,
      integrations: [
        Sentry.browserTracingIntegration(),
        // Text inputs stay masked. The rest of the screen is the game, which a
        // replay is no use without; .sentry-mask hides anything else.
        Sentry.replayIntegration({ maskAllText: false, blockAllMedia: false }),
        // Three of the games draw on a <canvas>, which replays leave blank without this.
        Sentry.replayCanvasIntegration(),
      ],
      tracesSampleRate: TRACES,
      replaysSessionSampleRate: REPLAYS,
      replaysOnErrorSampleRate: 1,
      beforeSend,
      dataCollection: { userInfo: false },
      // Tags label errors and replays; attributes label the spans of a trace.
      initialScope: { tags: { game }, attributes: { game } },
    });
    early.forEach((error) => Sentry.captureException(error, { mechanism: { handled: false } }));
  };

  SDK.forEach(({ src, integrity }, index) => {
    const script = document.createElement('script');
    // Dynamic scripts run as they arrive unless async is off; the add-on needs the bundle first.
    Object.assign(script, { src, integrity, crossOrigin: 'anonymous', async: false });
    if (index === SDK.length - 1) script.onload = init;
    script.onerror = () => { stopKeeping(); early.length = 0; };
    document.head.append(script);
  });
})();
