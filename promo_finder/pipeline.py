"""Run the whole thing: parse -> layer 1 candidates -> layer 2 model scores -> ranked promos.

    py -m promo_finder.pipeline data/scripts --out raw_outputs
    py -m promo_finder.pipeline data/scripts --out raw_outputs --skip-llm      (layer 1 only, no API key needed)
    py -m promo_finder.pipeline data/scripts --out raw_outputs --dry-run      (saved replies only, no API calls)
    py -m promo_finder.pipeline data/scripts --out outputs/trial --episodes 1-5 (a quick trial)

Everything written to the output folder is exactly what the code and the model produced.
The Streamlit app calls run_pipeline() with the same code path as the command line.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .candidates import find_candidates
from .parser import parse_folder

CSV_COLUMNS = [
    "rank", "status", "replaced_by", "id", "kind", "final_score", "hook_score", "cliffhanger_score",
    "standalone_score", "duration_seconds", "segments", "hook_line", "cliffhanger_line", "why_it_works",
    "key_moment", "rule_score", "hook_line_found", "hook_in_first_3s", "cliffhanger_line_found", "cliffhanger_at_end",
]


@dataclass
class RunOptions:
    per_episode: int = 3  # single-stretch candidates kept per episode
    stitched: int = 20  # two-segment candidates kept overall
    episodes: str | None = None  # e.g. "1-5"
    skip_llm: bool = False  # stop after layer 1
    dry_run: bool = False  # use saved replies only, never call the model
    delay: float = 5.0
    retries: int = 5
    force: bool = False
    episodes_per_call: int = 5
    stitched_per_call: int = 10
    cfg: object = None  # LLMConfig; None means read .env
    weights: object = None  # RankWeights; None means read .env


def where(row: dict) -> str:
    return " + ".join(f"ep{s['episode']} {s['start']}-{s['end']}" for s in row["segments"])


def promos_csv(promos: list[dict]) -> str:
    buf = io.StringIO()
    out = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\n")
    out.writeheader()
    for p in promos:
        out.writerow(p | p.get("checks", {}) | {"segments": where(p)})
    return buf.getvalue()


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_episode_files(folder: Path, episodes, candidates, promos: list[dict]) -> None:
    """One JSON per episode: its layer 1 candidates (with the clip lines) and what the model said about each."""
    folder.mkdir(parents=True, exist_ok=True)
    result = {p["id"]: p for p in promos}
    for ep in episodes:
        mine = [c for c in candidates if any(s.episode == ep.number for s in c.segments)]
        _write(folder / f"episode-{ep.number:03d}.json", {
            "episode": ep.number,
            "source_file": ep.source_file,
            "duration_seconds": ep.duration,
            "format_warnings": ep.warnings,
            "candidates": [c.to_dict() | {"result": result.get(c.id)} for c in mine],
        })


def run_pipeline(folder: Path, out: Path, opts: RunOptions, log=print) -> dict:
    """Run everything and write the output folder. Returns the summary, with the ranked promos under "promos".

    If the run cannot finish (quota used up), the summary has a "stopped" message instead of promos.
    """
    started = datetime.now()
    t0 = time.perf_counter()
    episodes = parse_folder(folder)
    if opts.episodes:
        lo, _, hi = opts.episodes.partition("-")
        episodes = [e for e in episodes if e.number is not None and int(lo) <= e.number <= int(hi or lo)]
    if not episodes:
        raise ValueError(f"No episodes found in {folder}")
    warned = sum(bool(e.warnings) for e in episodes)
    log(f"Parsed {len(episodes)} episodes ({warned} with format warnings)")

    candidates = find_candidates(episodes, opts.per_episode, opts.stitched)
    singles = sum(c.kind == "single" for c in candidates)
    layer1_seconds = time.perf_counter() - t0
    log(f"Layer 1: {len(candidates)} candidates ({singles} single stretch, {len(candidates) - singles} stitched) in {layer1_seconds:.1f}s")
    out.mkdir(parents=True, exist_ok=True)
    _write(out / "candidates.json", [c.to_dict() for c in candidates])
    if opts.skip_llm:
        return {"episodes": len(episodes), "candidates": len(candidates), "layer1_seconds": round(layer1_seconds, 1), "promos": []}

    from . import llm
    from .config import load_config, load_weights
    from .ranking import rank
    from .scorer import QuotaExhausted, group_duplicates, score_candidates

    cfg = opts.cfg or load_config()
    weights = opts.weights or load_weights()
    raw_dir = out / "llm_raw"
    usage_before = dict(llm.USAGE)
    log(f"Layer 2: scoring with {cfg.provider} / {cfg.model}" + (" (dry run: saved replies only)" if opts.dry_run else ""))
    t1 = time.perf_counter()
    common = dict(delay=opts.delay, retries=opts.retries, force=opts.force, log=log, cfg=cfg, dry_run=opts.dry_run)
    try:
        scores, failures = score_candidates(candidates, raw_dir, episodes_per_call=opts.episodes_per_call,
                                            stitched_per_call=opts.stitched_per_call, **common)
        groups, group_error = group_duplicates(candidates, scores, raw_dir, **common)
    except QuotaExhausted as exc:
        log(f"STOPPED: {exc}")
        return {"stopped": str(exc), "episodes": len(episodes), "candidates": len(candidates), "promos": []}
    layer2_seconds = time.perf_counter() - t1
    if group_error:
        log(f"Duplicate check failed, so no promos are marked duplicate: {group_error[:200]}")

    promos = rank(candidates, scores, groups, weights)
    count = {k: sum(p["status"] == k for p in promos) for k in ("selected", "overlap", "duplicate")}
    flagged = [p for p in promos if not all(p["checks"].values())]
    usage = {k: llm.USAGE[k] - usage_before[k] for k in llm.USAGE}
    summary = {
        "started": started.isoformat(timespec="seconds"),
        "model": f"{cfg.provider}/{cfg.model}",
        "dry_run": opts.dry_run,
        "rank_weights": {"hook": weights.hook, "cliffhanger": weights.cliffhanger, "standalone": weights.standalone},
        "episodes": len(episodes),
        "candidates": len(candidates),
        "scored": len(promos),
        "unscored": len(candidates) - len(promos),
        "status_counts": count,
        "failed_quote_check": len(flagged),
        "layer1_seconds": round(layer1_seconds, 1),
        "layer2_seconds": round(layer2_seconds, 1),
        "total_seconds": round(time.perf_counter() - t0, 1),
        "delay_between_calls_seconds": opts.delay,
        "episodes_per_call": opts.episodes_per_call,
        "api_usage": usage,
        "failed_batches": failures,
        "duplicate_check_error": group_error or None,
        "duplicate_groups": groups,
    }
    _write(out / "promos_ranked.json", summary | {"promos": promos})
    (out / "promos_ranked.csv").write_text(promos_csv(promos), encoding="utf-8-sig")  # utf-8-sig so Excel reads it
    _write_episode_files(out / "episodes", episodes, candidates, promos)
    _write(out / "run_summary.json", summary)
    log(f"Wrote {out}: promos_ranked.json, promos_ranked.csv, episodes/ ({len(episodes)} files), llm_raw/, run_summary.json")
    return summary | {"promos": promos}


def main() -> int:
    ap = argparse.ArgumentParser(description="Find and rank promo clips in a folder of screenplays.")
    ap.add_argument("folder", type=Path, help="folder containing the episode .txt files")
    ap.add_argument("--out", type=Path, default=Path("raw_outputs"), help="output folder (default: raw_outputs)")
    ap.add_argument("--per-episode", type=int, default=3, help="single-stretch candidates kept per episode")
    ap.add_argument("--stitched", type=int, default=20, help="two-segment candidates kept overall (0 to turn off)")
    ap.add_argument("--episodes", help="only these episodes, e.g. 1-5")
    ap.add_argument("--skip-llm", action="store_true", help="stop after layer 1")
    ap.add_argument("--dry-run", action="store_true", help="use saved replies only, never call the model")
    ap.add_argument("--delay", type=float, default=5.0, help="seconds to wait between model calls")
    ap.add_argument("--retries", type=int, default=5, help="attempts per model call, with a growing wait between them")
    ap.add_argument("--episodes-per-call", type=int, default=5, help="episodes scored in one model call (more = fewer requests)")
    ap.add_argument("--stitched-per-call", type=int, default=10, help="stitched candidates scored in one model call")
    ap.add_argument("--force", action="store_true", help="ignore saved model replies and call again")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

    opts = RunOptions(args.per_episode, args.stitched, args.episodes, args.skip_llm, args.dry_run, args.delay,
                      args.retries, args.force, args.episodes_per_call, args.stitched_per_call)
    result = run_pipeline(args.folder, args.out, opts)
    if "stopped" in result:
        from . import llm

        print(f"  {llm.USAGE['calls']} calls sent this run, {llm.USAGE['failed_calls']} failed. No ranked files were written.")
        return 2
    if args.skip_llm:
        return 0

    promos, count, u, w = result["promos"], result["status_counts"], result["api_usage"], result["rank_weights"]
    print(f"  {len(promos)} scored, {result['unscored']} not scored, {len(result['failed_batches'])} batches failed")
    print(f"  {count['selected']} selected, {count['overlap']} marked overlap, {count['duplicate']} marked duplicate")
    print(f"  rank score = hook x {w['hook']} + cliffhanger x {w['cliffhanger']} + standalone x {w['standalone']}, scaled to 10")
    print(f"  {result['failed_quote_check']} of {len(promos)} have a quoted hook or cliffhanger that failed the code check")
    print(f"  time: layer 1 {result['layer1_seconds']}s, layer 2 {result['layer2_seconds'] / 60:.1f} min")
    print(f"  API: {u['calls']} calls sent, {u['failed_calls']} failed and were retried, "
          f"{u['input_tokens']:,} input tokens, {u['output_tokens']:,} output tokens (incl. {u['thinking_tokens']:,} thinking)")
    print("\nTop 10 selected")
    for p in [p for p in promos if p["status"] == "selected"][:10]:
        print(f"{p['rank']:>2}. {p['id']:<7} {p['final_score']:>5}/10  hook {p['hook_score']:.0f} cliff {p['cliffhanger_score']:.0f} "
              f"alone {p['standalone_score']:.0f}  {p['duration_seconds']:.0f}s  {where(p)}")
        print(f"      {p['key_moment']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
