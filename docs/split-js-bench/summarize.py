"""Medians of bench.py's runs: python3 docs/split-js-bench/summarize.py OUT.jsonl"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict


def main() -> None:
    rows = [json.loads(line) for line in open(sys.argv[1])]
    runs = defaultdict(list)
    for row in rows:
        for visit in ("cold", "repeat", "deploy"):
            if visit in row:
                runs[(row["profile"], visit, row["site"])].append(row[visit])
    print(f"{'profile':7} {'visit':7} {'site':10} {'n':>2} {'fcp':>6} {'drawn':>6} {'load':>6} {'kB':>6} {'req':>3}")
    for (profile, visit, site), found in sorted(runs.items()):
        median = {key: statistics.median(v[key] for v in found if v[key] is not None) for key in found[0]}
        print(
            f"{profile:7} {visit:7} {site:10} {len(found):>2} {median['fcp']:6.0f} {median['drawn']:6.0f}"
            f" {median['load']:6.0f} {median['bytes'] / 1000:6.1f} {median['requests']:3.0f}"
        )


if __name__ == "__main__":
    main()
