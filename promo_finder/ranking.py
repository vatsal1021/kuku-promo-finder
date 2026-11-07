"""Final ranking: weighted score, then keep one promo per stretch of time and per story beat.

Nothing is deleted. Every scored candidate stays in the output with a status:
  selected   ranked and worth posting
  overlap    shares screen time with a better promo
  duplicate  shows the same key moment as a better promo
"""

from __future__ import annotations

from .candidates import EPS, Candidate
from .config import RankWeights


def final_score(scores: dict, w: RankWeights) -> float:
    """Weighted average of the three model scores, on a 0 to 10 scale."""
    total = w.hook + w.cliffhanger + w.standalone
    raw = w.hook * scores["hook_score"] + w.cliffhanger * scores["cliffhanger_score"] + w.standalone * scores["standalone_score"]
    return round(raw / total, 2)


def shares_time(a: Candidate, b: Candidate) -> bool:
    """True if any segment of a overlaps any segment of b in the same episode."""
    return any(
        x.episode == y.episode and min(x.end, y.end) - max(x.start, y.start) > EPS
        for x in a.segments
        for y in b.segments
    )


def rank(candidates: list[Candidate], scores: dict[str, dict], groups: list[list[str]], weights: RankWeights) -> list[dict]:
    """Best first. Walks down the list and marks anything that clashes with a better promo above it."""
    group_of = {cid: n for n, group in enumerate(groups) for cid in group}
    scored = [c for c in candidates if c.id in scores]
    scored.sort(key=lambda c: (-final_score(scores[c.id], weights), -c.rule_score, c.id))

    selected: list[Candidate] = []
    rows = []
    for c in scored:
        row = {k: v for k, v in c.to_dict().items() if k != "lines"} | scores[c.id]
        row["final_score"] = final_score(scores[c.id], weights)
        row |= {"status": "selected", "rank": None, "replaced_by": None}

        clash = next((s for s in selected if shares_time(c, s)), None)
        twin = next((s for s in selected if c.id in group_of and group_of.get(s.id) == group_of[c.id]), None)
        if clash:
            row |= {"status": "overlap", "replaced_by": clash.id}
        elif twin:
            row |= {"status": "duplicate", "replaced_by": twin.id}
        else:
            selected.append(c)
            row["rank"] = len(selected)
        rows.append(row)

    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0, -r["final_score"]))
    return rows
