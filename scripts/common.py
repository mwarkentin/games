"""Settings and helpers shared by the build scripts."""

from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

BASE_URL = "https://games.michaelwarkentin.com"
SITE_NAME = "games.michaelwarkentin.com"
REPO_URL = "https://github.com/mwarkentin/games"
# The repo's issue forms: the header's "Feedback" link, and each game's "Send
# feedback" (data-feedback) without JavaScript. With it, feedback.js opens a
# dialog that sends to Sentry or links to the forms filled in.
FEEDBACK_URL = f"{REPO_URL}/issues/new/choose"
# The leaderboard Worker (worker/), which the games' LEADERBOARD_URL, ROOMS_URL
# and the survey log's SURVEY_URL name. A pull request's preview points them at
# its own Worker Preview instead (see scripts/point_preview.py).
WORKER_URL = "https://api.games.michaelwarkentin.com"
ROOT = Path(__file__).resolve().parent.parent
# The Stripe Payment Link for tips. While it's empty, pages have no tip link.
TIP_URL = "https://buy.stripe.com/4gM7sL3xucbG0ADgcd3Je00"

# Pages the build generates. A game can't use these filenames.
GENERATED_PAGES = {"index.html": "/", "colophon.html": "/colophon"}
# Each app's changelog: changelog/<app>.md, built into /changelog/<app> by
# build_changelog.py.
CHANGELOGS = "changelog"
# Counterscale page views, inlined into every page: games and generated pages.
ANALYTICS = "analytics.js"
# Home-screen apps (see scripts/build_pwa.py). Each game is its own app, named
# after its slug; the home page and colophon share the app called HOME_APP.
HOME_APP = "index"
# icons/<app>-<size>.png: an apple-touch-icon, and the manifest's two icons.
ICON_SIZES = (180, 192, 512)
# Link previews: previews/<app>.jpg, 1200x630, shown when a link to the page
# is shared. Apps without one use their 512px icon as a small card instead.
PREVIEWS = "previews"
PREVIEW_SIZE = (1200, 630)
# Registers sw.js, which keeps an offline copy of every page.
REGISTER_SERVICE_WORKER = """
if ('serviceWorker' in navigator) {
  addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}
"""


def insert_in_head(text: str, tags: str) -> str:
    """Insert tags just before </head>, or at the end of a page without one."""
    index = text.lower().find("</head>")
    if index == -1:
        return f"{text.rstrip()}\n{tags}"
    return f"{text[:index]}{tags}{text[index:]}"


def inline_script(text: str, marker: str, script: str, attrs: str = "") -> str:
    """Inline a script before </head>, or at the end, once.

    The tag is <script {marker}{attrs}>, and a page that already has one is
    left as it is. Inline rather than a file, so it runs without waiting for
    another request.
    """
    if f"<script {marker}" in text:
        return text
    return insert_in_head(text, f"<script {marker}{attrs}>\n{script.strip()}\n</script>\n")


def inject_pwa(text: str, app: str) -> str:
    """Link a page to its app's manifest and icons, and register sw.js, once."""
    if "<script data-pwa" in text:
        return text
    tags = (
        f'<link rel="manifest" href="/manifests/{app}.webmanifest">\n'
        f'<link rel="icon" type="image/png" sizes="192x192" href="/icons/{app}-192.png">\n'
        f'<link rel="apple-touch-icon" href="/icons/{app}-180.png">\n'
    )
    return inline_script(insert_in_head(text, tags), "data-pwa", REGISTER_SERVICE_WORKER)


def inject_social(text: str, app: str, path: str, root: Path | None = None) -> str:
    """Add Open Graph and Twitter card tags, so a shared link shows a card.

    Title and description come from the page's own <head>. The image is
    previews/<app>.jpg as a large card if the app has one, or else its 512px
    icon as a small one. Every URL is absolute, as link unfurlers need. A page
    that already has og:title is left as it is.
    """
    if re.search(r"""property\s*=\s*["']og:title["']""", text, re.IGNORECASE):
        return text
    title = extract_title(text, app)
    description = extract_meta_description(text)
    if ((root or ROOT) / PREVIEWS / f"{app}.jpg").exists():
        image, (width, height), card = f"{BASE_URL}/{PREVIEWS}/{app}.jpg", PREVIEW_SIZE, "summary_large_image"
    else:
        image, (width, height), card = f"{BASE_URL}/icons/{app}-512.png", (512, 512), "summary"
    tags = [
        ("property", "og:type", "website"),
        ("property", "og:site_name", SITE_NAME),
        ("property", "og:title", title),
        *([("property", "og:description", description)] if description else []),
        ("property", "og:url", f"{BASE_URL}{path}"),
        ("property", "og:image", image),
        ("property", "og:image:width", str(width)),
        ("property", "og:image:height", str(height)),
        ("name", "twitter:card", card),
    ]
    return insert_in_head(
        text, "".join(f'<meta {kind}="{key}" content="{html.escape(value)}">\n' for kind, key, value in tags)
    )


def preview_files(root: Path = ROOT) -> list[str]:
    """The link-preview images, as paths like previews/foo.jpg."""
    return sorted(f"{PREVIEWS}/{path.name}" for path in (root / PREVIEWS).glob("*.jpg"))


def inject_analytics(text: str, root: Path | None = None) -> str:
    """Inline analytics.js into a page."""
    script = ((root or ROOT) / ANALYTICS).read_text("utf-8")
    return inline_script(text, "data-analytics", script)


def music_files(root: Path = ROOT) -> list[str]:
    """The MIDI files games play, as paths like music/foo.mid (see music/README.md)."""
    return sorted(f"music/{path.name}" for path in (root / "music").glob("*.mid"))


def game_files(root: Path = ROOT) -> list[str]:
    """Every game: the .html files at the top level of the repo.

    That includes pages that belong to a game, like Letterfield's survey log:
    they're published, listed and tested the same way, but join their game's
    home-screen app (see app_of).
    """
    return sorted(
        path.name
        for path in root.glob("*.html")
        if path.name not in GENERATED_PAGES
    )


def changelog_apps(root: Path = ROOT) -> list[str]:
    """The apps with a changelog, by slug."""
    return sorted(path.stem for path in (root / CHANGELOGS).glob("*.md"))


def changelog_path(app: str) -> str:
    """Where an app's changelog is served."""
    return f"/{CHANGELOGS}/{app}"


def generated_pages(root: Path = ROOT) -> dict[str, str]:
    """Every page the build generates, as {file in the site: path it's served at}:
    the home page, the colophon and each app's changelog."""
    return {
        **GENERATED_PAGES,
        **{f"{CHANGELOGS}/{app}.html": changelog_path(app) for app in changelog_apps(root)},
    }


def app_of(text: str, slug: str) -> str:
    """The home-screen app a page belongs to: its own, named after its slug,
    unless its <head> names a game's with <meta name="games:app" content="...">.

    A page in another game's app shares that game's manifest, icons and link
    preview, and opens inside it on a Home Screen, since its path starts with
    the game's (/letterfield-log is in /letterfield's scope).
    """
    return extract_meta(text, "games:app") or slug


def own_apps(root: Path = ROOT) -> list[str]:
    """The games that are home-screen apps of their own, by slug."""
    slugs = [filename.removesuffix(".html") for filename in game_files(root)]
    return [slug for slug in slugs if app_of((root / f"{slug}.html").read_text("utf-8"), slug) == slug]


def extract_title(text: str, fallback: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    return html.unescape(match.group(1).strip()) if match else fallback


def extract_meta(text: str, name: str) -> str:
    """The content of the first <meta name="{name}">, or ""."""
    for tag in re.findall(r"<meta\b[^>]*>", text, re.IGNORECASE):
        if re.search(rf"""name\s*=\s*["']{re.escape(name)}["']""", tag, re.IGNORECASE):
            match = re.search(r"""content\s*=\s*(["'])(.*?)\1""", tag, re.DOTALL)
            if match:
                return html.unescape(match.group(2).strip())
    return ""


def extract_meta_description(text: str) -> str:
    return extract_meta(text, "description")


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_date(value: datetime) -> str:
    return f"{value:%b} {value.day}, {value.year}"


PAGE_CSS = """
:root {
  color-scheme: light dark;
  --bg: #ffffff;
  --fg: #1b1b1b;
  --muted: #666666;
  --link: #0a5bc4;
  --rule: #e2e2e2;
  --panel: #f5f5f5;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #141414;
    --fg: #e6e6e6;
    --muted: #9a9a9a;
    --link: #78b4ff;
    --rule: #333333;
    --panel: #1f1f1f;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
.bar, main { max-width: 46rem; margin: 0 auto; padding: 0 16px; }
.bar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.25rem 1rem;
  padding-top: 0.9rem;
  padding-bottom: 0.9rem;
}
.bar .home { font-weight: 600; color: var(--fg); text-decoration: none; }
.bar nav a { margin-left: 1rem; }
.bar nav a:first-child { margin-left: 0; }
header { border-bottom: 1px solid var(--rule); }
main { padding-bottom: 3rem; }
a { color: var(--link); }
h1 { font-size: 1.6rem; line-height: 1.25; margin: 1.5rem 0 0.75rem; overflow-wrap: anywhere; }
h2 { font-size: 1.2rem; margin: 2rem 0 0.5rem; }
code {
  background: var(--panel);
  border-radius: 4px;
  padding: 0.1em 0.35em;
  font-size: 0.9em;
}
li { margin: 0.3rem 0; }
.muted { color: var(--muted); }
"""


def tip_link(source: str) -> str:
    """TIP_URL tagged with where the tip came from, so Stripe shows it on the payment.

    client_reference_id allows only letters, digits, dashes and underscores;
    Stripe drops anything else.
    """
    reference = re.sub(r"[^A-Za-z0-9_-]", "_", source)
    separator = "&" if "?" in TIP_URL else "?"
    return f"{TIP_URL}{separator}{urlencode({'client_reference_id': reference})}"


def render_page(
    title: str, body: str, *, path: str = "/", extra_css: str = "", description: str = "", tip_source: str = ""
) -> str:
    """Wrap generated content in the shared page chrome, with analytics.

    Generated pages belong to the home-screen app for the whole site, and
    share its link preview. path is where the page is served, for og:url.

    tip_source labels the header's tip link, which appears once TIP_URL is set.
    """
    meta = (
        f'\n<meta name="description" content="{html.escape(description)}">'
        if description
        else ""
    )
    tip = (
        f'<a href="{html.escape(tip_link(tip_source or "games"))}">Tip jar</a>'
        if TIP_URL
        else ""
    )
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">{meta}
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#ffffff">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#141414">
<title>{html.escape(title)}</title>
<style>{PAGE_CSS}{extra_css}</style>
</head>
<body>
<header>
  <div class="bar">
    <a class="home" href="/">{SITE_NAME}</a>
    <nav><a href="/colophon">Colophon</a><a href="{REPO_URL}">GitHub</a><a href="{FEEDBACK_URL}">Feedback</a>{tip}</nav>
  </div>
</header>
<main>
{body}
</main>
</body>
</html>
"""
    return inject_pwa(inject_analytics(inject_social(page, HOME_APP, path)), HOME_APP)
