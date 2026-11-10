// The "Send feedback" dialog, inlined into every game's <head> by
// scripts/publish.py. Each game has one link marked data-feedback that goes
// to the repo's issue forms; this opens a dialog instead. Once telemetry.js
// has loaded Sentry, the dialog is a form that sends to Sentry's User
// Feedback with the replay's last minute. Either way it links to the Bug and
// Idea forms, filled in with the game, the device and browser, and details of
// the page, all of which the player sees and can edit before sending.
// tests/test_feedback.py covers it, and tests/test_telemetry.py the Sentry form.
(() => {
  const ISSUES = 'https://github.com/mwarkentin/games/issues/new';

  // "War: Slam Edition" is War, and a pull request's preview drops its "PR 12 · ".
  const gameName = () => document.title.replace(/^PR \d+ · /, '').split(': ')[0];

  // A short "iPhone · iOS 18.5 · Safari 18.5" from the user agent. The whole
  // user agent goes in the details too, so this only needs to read well.
  const deviceAndBrowser = () => {
    const ua = navigator.userAgent;
    const ios = ua.match(/(iPhone|iPad|iPod).*? OS (\d+)_(\d+)/);
    const system = ios ? `${ios[1]} · iOS ${ios[2]}.${ios[3]}`
      // iPads ask for desktop sites, as a Mac with a touch screen.
      : /Macintosh/.test(ua) && navigator.maxTouchPoints > 1 ? 'iPad'
      : /Android/.test(ua) ? `Android ${(ua.match(/Android ([\d.]+)/) || [])[1] || ''}`.trim()
      : /Mac OS X/.test(ua) ? 'Mac'
      : /Windows/.test(ua) ? 'Windows'
      : /CrOS/.test(ua) ? 'ChromeOS'
      : /Linux/.test(ua) ? 'Linux' : '';
    // Most specific first: Edge and Samsung Internet say Chrome too, and every
    // browser on iOS says Safari. Links shared on social sites often open in
    // the app's own browser.
    const browsers = [
      [/Instagram/, "Instagram's browser"],
      [/FBAN|FBAV/, "Facebook's browser"],
      [/LinkedInApp/, "LinkedIn's browser"],
      [/EdgA?\/(\d+)|EdgiOS\/(\d+)/, 'Edge'],
      [/SamsungBrowser\/(\d+)/, 'Samsung Internet'],
      [/Firefox\/(\d+)|FxiOS\/(\d+)/, 'Firefox'],
      [/Chrome\/(\d+)|CriOS\/(\d+)/, 'Chrome'],
      [/Version\/([\d.]+).*Safari/, 'Safari'],
    ];
    const [pattern, name] = browsers.find(([re]) => re.test(ua)) || [];
    const version = pattern && ua.match(pattern).slice(1).find(Boolean);
    const browser = name ? [name, version].filter(Boolean).join(' ') : '';
    return [system, browser].filter(Boolean).join(' · ') || ua;
  };

  // The address without its query string or fragment, which can hold room and
  // group invite codes.
  const details = () => {
    const html = document.documentElement;
    const state = Object.entries(html.dataset).map(([machine, at]) => `${machine}=${at}`).join(', ');
    const release = document.querySelector('script[data-telemetry]')?.dataset.release || '';
    const replay = window.Sentry?.getReplay?.()?.getReplayId?.();
    const scheme = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    const app = matchMedia('(display-mode: standalone)').matches || navigator.standalone
      ? 'Home Screen app' : 'browser tab';
    return [
      `Page: ${location.origin}${location.pathname}`,
      state && `State: ${state}`,
      `Window: ${innerWidth}×${innerHeight} at ${devicePixelRatio}×, ${scheme} mode, ${app}`,
      release && `Version: ${release.slice(0, release.indexOf('@') + 8)}`,
      replay && `Sentry replay: ${replay}`,
      `User agent: ${navigator.userAgent}`,
    ].filter(Boolean).join('\n');
  };

  // Field names are the ids in .github/ISSUE_TEMPLATE/bug.yml and idea.yml.
  const issueUrl = (kind, message = '') => {
    const game = gameName();
    message = message.trim().slice(0, 2000);
    const fields = kind === 'bug'
      ? { template: 'bug.yml', title: `${game}: `, game, what: message, device: deviceAndBrowser(), details: details() }
      : { template: 'idea.yml', title: `${game}: `, game, idea: message };
    return `${ISSUES}?${new URLSearchParams(Object.entries(fields).filter(([, value]) => value))}`;
  };

  const sentry = () => Boolean(window.Sentry?.getClient?.());
  let dialog, thanks;

  const build = () => {
    const style = document.createElement('style');
    style.textContent = `
.games-feedback{color-scheme:light dark;box-sizing:border-box;width:min(92vw,420px);border:0;border-radius:14px;padding:20px;background:Canvas;color:CanvasText;font:16px/1.4 system-ui,sans-serif;box-shadow:0 12px 40px rgb(0 0 0/.35)}
.games-feedback::backdrop{background:rgb(0 0 0/.5)}
.games-feedback[data-mode=github] [data-for=sentry],.games-feedback[data-mode=sentry] [data-for=github]{display:none}
.games-feedback :is(h2,p,label,button,a){text-transform:none;letter-spacing:normal}
.games-feedback h2{margin:0 0 6px;font:700 18px/1.3 system-ui,sans-serif}
.games-feedback p{margin:0 0 10px;font-size:14px}
.games-feedback label{display:block;margin:12px 0 4px;font-size:14px}
.games-feedback textarea,.games-feedback input{box-sizing:border-box;width:100%;padding:10px;border:1px solid GrayText;border-radius:8px;background:Field;color:FieldText;font:16px/1.4 system-ui,sans-serif}
.games-feedback textarea{min-height:120px;resize:vertical}
.games-feedback .games-feedback-row{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;margin:16px 0 10px}
.games-feedback [data-for=github] .games-feedback-row{flex-direction:column-reverse;align-items:stretch;text-align:center}
.games-feedback a{color:inherit}
.games-feedback :is(button,.games-feedback-button){padding:10px 16px;border:1px solid GrayText;border-radius:8px;background:ButtonFace;color:ButtonText;font:600 16px/1.2 system-ui,sans-serif;text-decoration:none;cursor:pointer}
.games-feedback :is(button[type=submit],.games-feedback-primary){border-color:CanvasText;background:CanvasText;color:Canvas}`;
    document.head.append(style);

    const github = (kind, text, className = '') =>
      `<a href="${ISSUES}/choose" target="_blank" rel="noopener" data-issue="${kind}"${className && ` class="${className}"`}>${text}</a>`;
    const el = document.createElement('dialog');
    el.className = 'games-feedback';
    el.setAttribute('aria-labelledby', 'games-feedback-title');
    el.innerHTML = `<h2 id="games-feedback-title">Send feedback</h2>
<form data-for="sentry">
<p>Found a bug, or have an idea? The last minute of play comes with it, so I can see what happened. Anything you type here is hidden.</p>
<label for="games-feedback-message">What happened, or what's your idea?</label>
<textarea id="games-feedback-message" name="message" required maxlength="4000" class="sentry-mask"></textarea>
<label for="games-feedback-email">Your email, if you'd like a reply (optional)</label>
<input id="games-feedback-email" name="email" type="email" autocomplete="email" class="sentry-mask">
<div class="games-feedback-row"><button type="button" value="cancel">Cancel</button><button type="submit">Send</button></div>
<p>Or on GitHub: ${github('bug', 'report a bug')} or ${github('idea', 'suggest an idea')}</p>
</form>
<div data-for="github">
<p>Found a bug, or have an idea? Tell me on GitHub. The form comes filled in with the game and your device, so you only need to say what happened, and you'll see everything before you send it.</p>
<div class="games-feedback-row"><button type="button" value="cancel">Cancel</button>${github('idea', 'Suggest an idea', 'games-feedback-button')}${github('bug', 'Report a bug', 'games-feedback-button games-feedback-primary')}</div>
</div>`;
    // Keys, taps and clicks stay in the dialog, so they don't steer the game behind it.
    ['keydown', 'keyup', 'keypress', 'pointerdown', 'pointerup', 'touchstart', 'touchmove', 'wheel', 'click']
      .forEach((type) => el.addEventListener(type, (event) => event.stopPropagation()));
    el.querySelectorAll('button[value=cancel]').forEach((button) => button.addEventListener('click', () => el.close()));

    const form = el.querySelector('form');
    // Filled in as it's followed, so it carries anything typed in the form,
    // and the replay so far is sent for the issue to point to.
    el.querySelectorAll('a[data-issue]').forEach((link) => link.addEventListener('click', () => {
      link.href = issueUrl(link.dataset.issue, el.dataset.mode === 'sentry' ? form.message.value : '');
      window.Sentry?.getReplay?.()?.flush?.()?.catch?.(() => {});
      setTimeout(() => el.close());
    }));
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const message = form.message.value.trim();
      if (!message || !sentry()) return;
      Sentry.captureFeedback({ message, email: form.email.value.trim() || undefined }, { includeReplay: true });
      form.reset();
      el.querySelector('h2').textContent = 'Thanks! Sent.';
      thanks = setTimeout(() => el.close(), 1500);
    });
    document.body.append(el);
    return el;
  };

  const open = () => {
    dialog ??= build();
    // A "Thanks" still showing from the last one mustn't close this one.
    clearTimeout(thanks);
    dialog.dataset.mode = sentry() ? 'sentry' : 'github';
    dialog.querySelector('h2').textContent = 'Send feedback';
    // Ready for a long press or a right click, which skip the click handler.
    dialog.querySelectorAll('a[data-issue]').forEach((link) => { link.href = issueUrl(link.dataset.issue); });
    if (!dialog.open) dialog.showModal();
    dialog.querySelector(dialog.dataset.mode === 'sentry' ? 'textarea' : '.games-feedback-primary').focus();
  };

  // Capturing, so a game that stops clicks in its menus can't swallow this
  // one. A click meant for a new tab still goes to GitHub.
  addEventListener('click', (event) => {
    const link = event.target instanceof Element && event.target.closest('[data-feedback]');
    if (!link || event.button || event.metaKey || event.ctrlKey || event.shiftKey) return;
    event.preventDefault();
    open();
  }, true);
})();
