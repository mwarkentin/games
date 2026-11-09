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
      tracesSampleRate: 1,
      replaysSessionSampleRate: 0.1,
      replaysOnErrorSampleRate: 1,
      dataCollection: { userInfo: false },
      // Tags label errors and replays; attributes label the spans of a trace.
      initialScope: { tags: { game }, attributes: { game } },
    });
    early.forEach((error) => Sentry.captureException(error, { mechanism: { handled: false } }));
    wireFeedback();
  };

  // Feedback. Every game has a "Send feedback" link marked data-feedback that
  // goes to GitHub issues. Once the SDK is here, it opens this form instead,
  // which sends to Sentry's User Feedback with the last minute of the replay
  // (includeReplay). Sentry.captureFeedback is in every CDN bundle; the
  // ready-made widget isn't in this one, and the game owns the screen anyway.
  const wireFeedback = () => {
    let dialog, thanks;
    const build = () => {
      const style = document.createElement('style');
      style.textContent = `
.games-feedback{color-scheme:light dark;box-sizing:border-box;width:min(92vw,420px);border:0;border-radius:14px;padding:20px;background:Canvas;color:CanvasText;font:16px/1.4 system-ui,sans-serif;box-shadow:0 12px 40px rgb(0 0 0/.35)}
.games-feedback::backdrop{background:rgb(0 0 0/.5)}
.games-feedback :is(h2,p,label,button){text-transform:none;letter-spacing:normal}.games-feedback h2{margin:0 0 6px;font:700 18px/1.3 system-ui,sans-serif}
.games-feedback p{margin:0 0 10px;font-size:14px}
.games-feedback label{display:block;margin:12px 0 4px;font-size:14px}
.games-feedback textarea,.games-feedback input{box-sizing:border-box;width:100%;padding:10px;border:1px solid GrayText;border-radius:8px;background:Field;color:FieldText;font:16px/1.4 system-ui,sans-serif}
.games-feedback textarea{min-height:120px;resize:vertical}
.games-feedback .games-feedback-row{display:flex;gap:8px;justify-content:flex-end;margin-top:16px}
.games-feedback button{padding:10px 16px;border:1px solid GrayText;border-radius:8px;background:ButtonFace;color:ButtonText;font:600 16px system-ui,sans-serif;cursor:pointer}
.games-feedback button[type=submit]{border-color:CanvasText;background:CanvasText;color:Canvas}
.games-feedback a{color:inherit}`;
      document.head.append(style);

      const el = document.createElement('dialog');
      el.className = 'games-feedback';
      el.setAttribute('aria-labelledby', 'games-feedback-title');
      el.innerHTML = `<form>
<h2 id="games-feedback-title">Send feedback</h2>
<p>Found a bug, or have an idea? The last minute of play comes with it, so I can see what happened. Anything you type there is hidden.</p>
<label for="games-feedback-message">What happened, or what's your idea?</label>
<textarea id="games-feedback-message" name="message" required maxlength="4000" class="sentry-mask"></textarea>
<label for="games-feedback-email">Your email, if you'd like a reply (optional)</label>
<input id="games-feedback-email" name="email" type="email" autocomplete="email" class="sentry-mask">
<div class="games-feedback-row"><button type="button" value="cancel">Cancel</button><button type="submit">Send</button></div>
<p><a href="https://github.com/mwarkentin/games/issues/new/choose" target="_blank" rel="noopener">Or open an issue on GitHub</a></p>
</form>`;
      // Keys and touches stay in the form, so typing doesn't steer the game behind it.
      ['keydown', 'keyup', 'keypress', 'pointerdown', 'pointerup', 'touchstart', 'touchmove', 'wheel']
        .forEach((type) => el.addEventListener(type, (event) => event.stopPropagation()));
      const form = el.querySelector('form');
      el.querySelector('button[value=cancel]').addEventListener('click', () => el.close());
      form.addEventListener('submit', (event) => {
        event.preventDefault();
        const message = form.message.value.trim();
        if (!message) return;
        Sentry.captureFeedback({ message, email: form.email.value.trim() || undefined }, { includeReplay: true });
        form.reset();
        el.querySelector('h2').textContent = 'Thanks! Sent.';
        thanks = setTimeout(() => el.close(), 1500);
      });
      document.body.append(el);
      return el;
    };
    // Capturing, so a game that stops clicks in its menus can't swallow this one.
    addEventListener('click', (event) => {
      const link = event.target instanceof Element && event.target.closest('[data-feedback]');
      if (!link || !Sentry.getClient()) return;
      event.preventDefault();
      dialog ??= build();
      // A "Thanks" still showing from the last one mustn't close this one.
      clearTimeout(thanks);
      dialog.querySelector('h2').textContent = 'Send feedback';
      if (!dialog.open) dialog.showModal();
      dialog.querySelector('textarea').focus();
    }, true);
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
