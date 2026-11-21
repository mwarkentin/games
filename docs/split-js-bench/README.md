# Measuring the split

The scripts behind the numbers in `docs/split-js.md`. Nothing here is part of
the site or its tests.

- `pages.mjs`: a stand-in for GitHub Pages (HTTP/2, gzip, `max-age=600`, ETags),
  with node's own modules only.
- `bench.py`: opens Letterfield over it in Chromium under DevTools' Fast 3G and
  Fast 4G presets with 4× CPU slowdown, and unthrottled: a first visit, a repeat
  visit, and a visit after a deploy.
- `variants.py`: the sites it compares, made from two builds.
- `summarize.py`: the medians.
- `coupling.mjs`: how tangled the page's sections are (needs two npm packages,
  outside the repo; see its header).

```sh
uv run ./build.sh                                   # this branch's site, in _site/
git worktree add /tmp/main main && (cd /tmp/main && SITE_DIR=/tmp/bench/base bash build.sh)
mv _site /tmp/bench/proto
python3 docs/split-js-bench/variants.py /tmp/bench
uv run docs/split-js-bench/bench.py /tmp/bench/runs.jsonl 5 \
  main=/tmp/bench/base,/tmp/bench/main-v2 proto=/tmp/bench/proto,/tmp/bench/proto-v2 \
  theme=/tmp/bench/proto,/tmp/bench/proto-v2t nopre=/tmp/bench/nopre full=/tmp/bench/full,/tmp/bench/full-v2
python3 docs/split-js-bench/summarize.py /tmp/bench/runs.jsonl
```

It needs `openssl` and `node`, and Playwright's Chromium (`uv run playwright install chromium`).
Close other work first: the timings are only as steady as the machine.
