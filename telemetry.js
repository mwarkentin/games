// Error reporting, performance and session replays through Sentry, inlined
// into every game's <head> by scripts/publish.py so it runs before the game.
// tests/test_telemetry.py covers it.
(() => {
  // The games project's DSN. While it's empty, nothing loads and nothing is sent.
  const SENTRY_DSN = '';
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

  // Errors from before the SDK arrives are kept and sent once it does.
  // Errors from cross-origin scripts arrive as "Script error." with no error
  // attached; Sentry ignores those too.
  const early = [];
  const keep = (event) => {
    if (event.error || 'reason' in event) early.push(event.error ?? event.reason);
  };
  addEventListener('error', keep);
  addEventListener('unhandledrejection', keep);

  const init = () => {
    removeEventListener('error', keep);
    removeEventListener('unhandledrejection', keep);
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
      tracesSampleRate: 1,
      replaysSessionSampleRate: 0.1,
      replaysOnErrorSampleRate: 1,
      dataCollection: { userInfo: false },
    });
    early.forEach((error) => Sentry.captureException(error, { mechanism: { handled: false } }));
  };

  SDK.forEach(({ src, integrity }, index) => {
    const script = document.createElement('script');
    // Dynamic scripts run as they arrive unless async is off; the add-on needs the bundle first.
    Object.assign(script, { src, integrity, crossOrigin: 'anonymous', async: false });
    if (index === SDK.length - 1) script.onload = init;
    document.head.append(script);
  });
})();
