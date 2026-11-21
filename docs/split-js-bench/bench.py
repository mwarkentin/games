"""Letterfield's first load, repeat visit and visit after a deploy, for docs/split-js.md.

    uv run docs/split-js-bench/bench.py OUT.jsonl RUNS NAME=DIR[,DEPLOYED_DIR] ...

Each NAME is a built site (build.sh's _site, or one of variants.py's); with a
second directory, the same site after a deploy that changed one thing. It
serves them with pages.mjs, like GitHub Pages, and opens /letterfield in
Chromium at a phone's size under DevTools' Fast 3G and Fast 4G presets (with
4x CPU slowdown) and unthrottled. Runs take turns between sites, so a busy
machine slows them alike. Every host but localhost fails to resolve, so
nothing reaches production (Playwright's request routing isn't used: it
turns off the HTTP cache). summarize.py prints the medians.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROFILES = {  # latency (ms), down and up (bytes/s), CPU slowdown
    "fast3g": {"latency": 562.5, "down": 1.47e6 / 8, "up": 675e3 / 8, "cpu": 4},
    "fast4g": {"latency": 165, "down": 9e6 / 8, "up": 1.5e6 / 8, "cpu": 4},
    "none": {"latency": 0, "down": -1, "up": -1, "cpu": 1},
}
# The first letter drawn on the map (from the glyph atlas): the game can be played.
HOOK = """
(() => {
  const draw = CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage = function (...a) {
    if (!window.__drawn && this.canvas.id === 'map') window.__drawn = performance.now();
    return draw.apply(this, a);
  };
})();
"""
METRICS = r"""() => {
  const n = performance.getEntriesByType('navigation')[0];
  const fcp = performance.getEntriesByName('first-contentful-paint')[0];
  const res = performance.getEntriesByType('resource').filter((r) => r.name.startsWith(location.origin));
  return { fcp: fcp ? fcp.startTime : null, drawn: window.__drawn || null, dcl: n.domContentLoadedEventEnd,
    load: n.loadEventEnd, bytes: n.transferSize + res.reduce((a, r) => a + r.transferSize, 0), requests: 1 + res.length };
}"""


def certificate(work: Path) -> str:
    """A self-signed certificate for localhost, and its key's hash for Chromium to trust."""
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", "/CN=localhost"]
        + ["-keyout", str(work / "key.pem"), "-out", str(work / "cert.pem")],
        check=True,
        capture_output=True,
    )
    pub = subprocess.run(
        ["openssl", "x509", "-in", str(work / "cert.pem"), "-pubkey", "-noout"], check=True, capture_output=True
    )
    der = subprocess.run(
        ["openssl", "pkey", "-pubin", "-outform", "der"], input=pub.stdout, check=True, capture_output=True
    )
    return base64.b64encode(hashlib.sha256(der.stdout).digest()).decode()


def visit(page, url: str) -> dict:
    page.goto("about:blank")
    page.goto(url, wait_until="load")
    page.wait_for_function("window.__drawn", timeout=180000)
    page.wait_for_timeout(200)
    return page.evaluate(METRICS)


def throttled(browser, profile: dict):
    context = browser.new_context(service_workers="block", viewport={"width": 390, "height": 844})
    context.add_init_script(HOOK)
    page = context.new_page()
    cdp = context.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.send(
        "Network.emulateNetworkConditions",
        {
            "offline": False,
            "latency": profile["latency"],
            "downloadThroughput": profile["down"],
            "uploadThroughput": profile["up"],
        },
    )
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": profile["cpu"]})
    return context, page


def main() -> None:
    out, runs = Path(sys.argv[1]), int(sys.argv[2])
    sites = [
        (arg.split("=")[0], [str(Path(d).resolve()) for d in arg.split("=")[1].split(",")]) for arg in sys.argv[3:]
    ]
    work = Path(tempfile.mkdtemp())
    spki = certificate(work)
    root, root0 = work / "root.txt", work / "root0.txt"
    root.write_text(sites[0][1][0])
    root0.write_text(sites[0][1][0])
    servers = [
        subprocess.Popen(
            ["node", str(HERE / "pages.mjs"), str(path), port, str(work)], env={**os.environ, "MAX_AGE": age}
        )
        for path, port, age in [(root, "8443", "600"), (root0, "8444", "0")]
    ]
    time.sleep(1)
    try:
        with sync_playwright() as p, out.open("a") as rows:
            args = [
                "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost",
                f"--ignore-certificate-errors-spki-list={spki}",
            ]
            browser = p.chromium.launch(args=args)
            for run in range(runs):
                for name, profile in PROFILES.items():
                    for site, dirs in sites:
                        root.write_text(dirs[0])
                        context, page = throttled(browser, profile)
                        cold = visit(page, "https://localhost:8443/letterfield")
                        repeat = visit(page, "https://localhost:8443/letterfield")  # the HTTP cache still fresh
                        context.close()
                        row = {"site": site, "profile": name, "run": run, "cold": cold, "repeat": repeat}
                        if len(dirs) > 1:  # a visit after a deploy, once the cache must revalidate
                            root0.write_text(dirs[0])
                            context, page = throttled(browser, profile)
                            visit(page, "https://localhost:8444/letterfield")
                            root0.write_text(dirs[1])
                            row["deploy"] = visit(page, "https://localhost:8444/letterfield")
                            context.close()
                        rows.write(json.dumps(row) + "\n")
                        rows.flush()
                        print(site, name, run, round(cold["drawn"]), cold["bytes"], flush=True)
            browser.close()
    finally:
        for server in servers:
            server.terminate()


if __name__ == "__main__":
    main()
