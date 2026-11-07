"""Make the public sample: the ranked list for the sample show with every quoted script line removed.

    py -m promo_finder.sample_results raw_outputs/promos_ranked.json sample_results/promos_ranked_public.json

Kept per promo: rank, status, id, kind, segments and timestamps, duration, key moment (the model's own
paraphrase), the three scores, the rank score and the code checks. Dropped: hook line, cliffhanger line,
why it works, and the rule reasons, because they quote the screenplay.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KEEP_PROMO = ("rank", "status", "replaced_by", "id", "kind", "duration_seconds", "segments", "key_moment",
              "hook_score", "cliffhanger_score", "standalone_score", "final_score", "checks")
KEEP_SUMMARY = ("started", "model", "rank_weights", "episodes", "candidates", "scored", "unscored", "status_counts",
                "failed_quote_check", "layer1_seconds", "layer2_seconds", "total_seconds", "episodes_per_call",
                "api_usage", "duplicate_groups")


def strip(full: dict) -> dict:
    out = {k: full[k] for k in KEEP_SUMMARY if k in full}
    out["note"] = ("Public sample: quoted hook and cliffhanger lines and the 'why it works' text are removed "
                   "because they quote the screenplay. The full results are in the raw outputs folder, shared separately.")
    out["promos"] = [{k: p[k] for k in KEEP_PROMO if k in p} for p in full["promos"]]
    return out


def main() -> int:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    data = strip(json.loads(src.read_text(encoding="utf-8")))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    text = dst.read_text(encoding="utf-8")
    for key in ("hook_line", "cliffhanger_line", "why_it_works", "rule_reasons", "lines"):
        assert f'"{key}"' not in text, key
    print(f"Wrote {dst}: {len(data['promos'])} promos, no quoted lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
