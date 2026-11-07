"""Layer 1: plain code rules, no AI.

Finds candidate promo windows of 20 to 60 seconds. Every start and end is a shot boundary
(a camera cut in the script) where nobody is mid-line, and a clip never starts in the middle
of an unfinished speech. Timestamps are always taken from the script, never invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import cues
from .parser import Block, Episode, fmt_time

MIN_LEN, MAX_LEN = 20.0, 60.0
HOOK_WINDOW = 3.0  # the brief: a hook in the first 3 seconds
END_WINDOW = 4.0  # how far back from the cut we look for a cliffhanger
EPS = 0.01


def _rx(stems: list[str]) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(re.escape(s) for s in stems) + ")", re.IGNORECASE)


PHYSICAL, SHOCK, INTENSE = _rx(cues.PHYSICAL), _rx(cues.SHOCK), _rx(cues.INTENSE)
SUSPENSE, RESOLVED = _rx(cues.SUSPENSE), _rx(cues.RESOLVED)


@dataclass
class Segment:
    episode: int
    start: float
    end: float

    @property
    def length(self) -> float:
        return round(self.end - self.start, 2)

    def to_dict(self) -> dict:
        return {
            "episode": self.episode,
            "start": fmt_time(self.start),
            "end": fmt_time(self.end),
            "start_seconds": self.start,
            "end_seconds": self.end,
            "length_seconds": self.length,
        }


@dataclass
class Candidate:
    id: str
    kind: str  # single | stitched
    segments: list[Segment]
    rule_score: float
    rule_reasons: list[str]
    lines: list[dict] = field(default_factory=list)  # blocks in the clip, with offsets from clip start

    @property
    def duration(self) -> float:
        return round(sum(s.length for s in self.segments), 2)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "duration_seconds": self.duration,
            "segments": [s.to_dict() for s in self.segments],
            "rule_score": self.rule_score,
            "rule_reasons": self.rule_reasons,
            "lines": self.lines,
        }


class Timeline:
    """One episode's blocks on a single clock, with the rule scores for any cut point."""

    def __init__(self, ep: Episode):
        self.ep = ep
        self.blocks: list[Block] = sorted((b for sc in ep.scenes for b in sc.blocks), key=lambda b: (b.start, b.end))
        self.dialogue = [b for b in self.blocks if b.kind == "dialogue"]
        self.scene_starts = [sc.start for sc in ep.scenes[1:] if sc.start is not None]
        self.end = ep.duration
        # Cuts may only land where the picture cuts: the start or end of a camera shot.
        shots = [b for b in self.blocks if b.kind == "camera"]
        cuts = {t for b in shots for t in (b.start, b.end) if t <= self.end + EPS} | {self.end}
        self.starts = sorted(t for t in cuts if self.safe(t) and not self.mid_speech(t))
        self.ends = sorted(t for t in cuts if self.safe(t))

    def safe(self, t: float) -> bool:
        """True if cutting at t does not split a spoken line."""
        return not any(d.start < t - EPS and d.end > t + EPS for d in self.dialogue)

    def mid_speech(self, t: float) -> bool:
        """True if a clip starting at t would open partway through someone's speech.

        That is: the first line heard continues a sentence ("...and it isn't you."), or the same
        speaker's previous line was left unfinished ("You let me come here..." then "You let me...").
        A new sentence from the same speaker is fine.
        """
        first = next((d for d in self.dialogue if d.start >= t - EPS), None)
        if first is None:
            return False
        opening = first.text.lstrip()
        if opening.startswith(("...", "…")) or opening[:1].islower():
            return True
        earlier = [d for d in self.dialogue if d.end <= t + EPS]
        if not earlier:
            return False
        prev = max(earlier, key=lambda d: d.end)
        last = prev.text.rstrip().rstrip("\"”'")
        unfinished = last.endswith(("...", "…")) or not last.endswith((".", "!", "?"))
        return unfinished and _plain(prev.speaker) == _plain(first.speaker)

    def hook(self, t: float) -> tuple[float, list[str]]:
        """Score what begins in the 3 seconds after a start point."""
        first = [b for b in self.blocks if t - EPS <= b.start < t + HOOK_WINDOW]
        spoken = [b for b in first if b.kind == "dialogue"]
        score, why = 0.0, []

        best, best_why = 0.0, ""
        for d in spoken:
            s, tags = 1.0, []
            if "!" in d.text:
                s, tags = s + 2, tags + ["exclamation"]
            if "?" in d.text:
                s, tags = s + 1, tags + ["question"]
            if SHOCK.search(d.text):
                s, tags = s + 2, tags + ["shock word"]
            if d.delivery and INTENSE.search(d.delivery):
                s, tags = s + 1, tags + ["intense delivery"]
            if len(d.text.split()) <= 7:
                s += 0.5
            if s > best:
                best, best_why = s, f'opens on line "{d.text[:50]}"' + (f" ({', '.join(tags)})" if tags else "")
        if spoken:
            score += best
            why.append(best_why)

        physical = [b for b in first if b.kind in ("action", "sound") and PHYSICAL.search(b.text)]
        on_camera = [b for b in first if b.kind == "camera" and PHYSICAL.search(b.text)]
        if physical:
            score += 3
            why.append(f"physical cue at open: {PHYSICAL.search(physical[0].text)[0].lower()}")
        elif on_camera:
            score += 1.5
            why.append(f"visual cue at open: {PHYSICAL.search(on_camera[0].text)[0].lower()}")

        if not spoken and not physical and not on_camera:
            score -= 3
            why.append("nothing happens in the first 3s")
        return min(score, 10.0), why

    def cliff(self, t: float) -> tuple[float, list[str]]:
        """Score what happens in the 4 seconds before an end point."""
        last = [b for b in self.blocks if t - END_WINDOW < b.end <= t + EPS]
        spoken = [b for b in last if b.kind == "dialogue"]
        score, why = 0.0, []

        if spoken:
            d = max(spoken, key=lambda b: b.end)
            text = d.text.rstrip()
            if text.endswith("?"):
                score += 2.5
                why.append(f'ends on unanswered question "{text[-50:]}"')
            elif text.endswith(("...", "…", "—", "-")):
                score += 2.5
                why.append(f'ends on unfinished line "{text[-50:]}"')
            elif text.endswith("!"):
                score += 1
                why.append(f'ends on shouted line "{text[-50:]}"')
            if SHOCK.search(text):
                score += 1.5
                why.append("last line has a shock word")
            if d.delivery and INTENSE.search(d.delivery):
                score += 0.5

        visual = [b for b in last if b.kind in ("action", "sound") and SUSPENSE.search(b.text)]
        on_camera = [b for b in last if b.kind == "camera" and SUSPENSE.search(b.text)]
        if visual:
            score += 3
            why.append(f"suspense cue at end: {SUSPENSE.search(visual[0].text)[0].lower()}")
        elif on_camera:
            score += 1.5
            why.append(f"visual suspense at end: {SUSPENSE.search(on_camera[0].text)[0].lower()}")

        if abs(t - self.end) < 0.05:
            score += 2
            why.append("ends where the episode ends")
        elif any(abs(t - s) < 0.05 for s in self.scene_starts):
            score += 0.5
            why.append("ends at a scene change")

        if any(b.kind != "dialogue" and RESOLVED.search(b.text) for b in last):
            score -= 2
            why.append("ending looks resolved")
        if not spoken and not visual and not on_camera:
            score -= 1
            why.append("flat ending")
        return min(score, 10.0), why

    def body(self, s: float, e: float) -> tuple[float, list[str]]:
        """Score the stretch between the cuts: density, intensity, confrontation, coherence."""
        dur = e - s
        inside = [b for b in self.blocks if b.start >= s - EPS and b.end <= e + EPS]
        spoken = [b for b in inside if b.kind == "dialogue"]
        score, why = 0.0, []

        density = sum(d.end - d.start for d in spoken) / dur
        score += min(density * 5, 3)
        heat = sum("!" in d.text for d in spoken) + sum(bool(d.delivery and INTENSE.search(d.delivery)) for d in spoken)
        heat += sum(bool(PHYSICAL.search(b.text)) for b in inside if b.kind in ("action", "sound"))
        score += min(heat / dur * 10, 3)
        why.append(f"dialogue fills {density:.0%}, {heat} emotional or physical cues")

        speakers = {d.speaker for d in spoken}
        if 2 <= len(speakers) <= 3:
            score += 1
            why.append(f"{len(speakers)}-person confrontation")
        changes = sum(s + 1 < t < e - 1 for t in self.scene_starts)
        if changes:
            score -= 1.5 * changes
            why.append(f"{changes} scene change(s) inside")

        edges = [s] + [x for d in spoken for x in (d.start, d.end)] + [e]
        silence = max(edges[i + 1] - edges[i] for i in range(0, len(edges), 2))
        if silence > 8:
            score -= 1
            why.append(f"{silence:.0f}s with no dialogue")
        return score, why

    def lines(self, s: float, e: float, offset: float = 0.0) -> list[dict]:
        """The blocks a viewer sees between s and e, with times measured from the start of the clip."""
        out = []
        for b in self.blocks:
            carried = b.kind != "dialogue" and b.start < s - EPS and b.end > s + 0.3
            if not carried and not (s - EPS <= b.start < e - EPS):
                continue
            out.append({
                "at": round(max(b.start, s) - s + offset, 2),
                "until": round(min(b.end, e) - s + offset, 2),
                "kind": b.kind,
                "speaker": b.speaker,
                "delivery": b.delivery,
                "voice": b.voice,
                "text": b.text,
                "already_running": carried,
            })
        return sorted(out, key=lambda x: x["at"])


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Shared time as a fraction of the shorter window."""
    shared = min(a[1], b[1]) - max(a[0], b[0])
    return max(shared, 0) / min(a[1] - a[0], b[1] - b[0])


def single_candidates(tl: Timeline, per_episode: int = 3, max_overlap: float = 0.3) -> list[Candidate]:
    """Best continuous 20-60s windows in one episode.

    Windows may overlap a little here, so the model sees alternative cuts of a strong stretch.
    The final ranking keeps only the better of any two that share time.
    """
    hooks = {s: tl.hook(s) for s in tl.starts}
    cliffs = {e: tl.cliff(e) for e in tl.ends}
    scored = []
    for s in tl.starts:
        for e in tl.ends:
            if MIN_LEN <= e - s <= MAX_LEN:
                b_score, b_why = tl.body(s, e)
                total = hooks[s][0] + cliffs[e][0] + 0.7 * b_score
                scored.append((round(total, 2), s, e, hooks[s][1] + cliffs[e][1] + b_why))
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))

    kept: list[tuple] = []
    for item in scored:
        if all(_overlap((item[1], item[2]), (k[1], k[2])) <= max_overlap for k in kept):
            kept.append(item)
            if len(kept) == per_episode:
                break

    out = []
    for rank, (total, s, e, why) in enumerate(kept):
        out.append(Candidate(
            id=f"E{tl.ep.number:03d}-{'ABCDEFGH'[rank]}",
            kind="single",
            segments=[Segment(tl.ep.number, s, e)],
            rule_score=total,
            rule_reasons=why,
            lines=tl.lines(s, e),
        ))
    return out


def _plain(name: str | None) -> str:
    """Speaker label with titles stripped, so 'LADY JULIANA' matches 'JULIANA'."""
    return re.sub(r"^(LADY|LORD|THE|FATHER|SIR)\s+", "", name or "")


def _who(tl: Timeline, s: float, e: float) -> set[str]:
    return {_plain(d.speaker) for d in tl.dialogue if d.start >= s - EPS and d.end <= e + EPS}


def _moments(tl: Timeline, per_episode: int = 2) -> tuple[list, list]:
    """Short hook moments (6-15s) and cliffhanger moments (12-35s) worth stitching."""
    hook_moments, cliff_moments = [], []
    for score, s in sorted(((tl.hook(s)[0], s) for s in tl.starts), reverse=True):
        ends = [e for e in tl.ends if 6 <= e - s <= 15]
        if score < 5 or not ends or any(abs(s - m[1]) < 15 for m in hook_moments):
            continue
        hook_moments.append((score, s, min(ends, key=lambda e: abs(e - s - 10))))
        if len(hook_moments) == per_episode:
            break
    for score, e in sorted(((tl.cliff(e)[0], e) for e in tl.ends), reverse=True):
        starts = [s for s in tl.starts if 12 <= e - s <= 35]
        if score < 5 or not starts or any(abs(e - m[2]) < 15 for m in cliff_moments):
            continue
        cliff_moments.append((score, min(starts, key=lambda s: abs(e - s - 20)), e))
        if len(cliff_moments) == per_episode:
            break
    return hook_moments, cliff_moments


def stitched_candidates(timelines: list[Timeline], limit: int = 20, max_episode_gap: int = 2) -> list[Candidate]:
    """Two-segment promos: a strong hook moment joined to a later cliffhanger moment that shares a character."""
    moments = {tl.ep.number: _moments(tl) for tl in timelines}
    by_number = {tl.ep.number: tl for tl in timelines}
    pairs = []
    for a, tl_a in by_number.items():
        for h_score, hs, he in moments[a][0]:
            for b in range(a, a + max_episode_gap + 1):
                if b not in by_number:
                    continue
                tl_b = by_number[b]
                for c_score, cs, ce in moments[b][1]:
                    if a == b and cs < he + 5:  # same episode: must be a real jump, not one stretch
                        continue
                    if not MIN_LEN <= (he - hs) + (ce - cs) <= MAX_LEN:
                        continue
                    shared = _who(tl_a, hs, he) & _who(tl_b, cs, ce)
                    if not shared:
                        continue
                    total = h_score + c_score + min(len(shared), 2) - (b - a)
                    pairs.append((round(total, 2), a, hs, he, b, cs, ce, sorted(shared)))
    pairs.sort(key=lambda p: (-p[0], p[1], p[2]))

    out, used = [], set()
    for total, a, hs, he, b, cs, ce, shared in pairs:
        if (a, hs) in used or (b, ce) in used:
            continue  # each moment is used once, so the list is not 20 versions of one clip
        used |= {(a, hs), (b, ce)}
        tl_a, tl_b = by_number[a], by_number[b]
        why = tl_a.hook(hs)[1] + tl_b.cliff(ce)[1] + [f"segments share {', '.join(shared)}"]
        out.append(Candidate(
            id=f"X{len(out) + 1:02d}",
            kind="stitched",
            segments=[Segment(a, hs, he), Segment(b, cs, ce)],
            rule_score=total,
            rule_reasons=why,
            lines=tl_a.lines(hs, he) + [{"cut": True, "at": round(he - hs, 2)}] + tl_b.lines(cs, ce, offset=he - hs),
        ))
        if len(out) == limit:
            break
    return out


def find_candidates(episodes: list[Episode], per_episode: int = 3, stitched: int = 20) -> list[Candidate]:
    timelines = [Timeline(ep) for ep in episodes if ep.number is not None and ep.duration >= MIN_LEN]
    singles = [c for tl in timelines for c in single_candidates(tl, per_episode)]
    return singles + (stitched_candidates(timelines, stitched) if stitched else [])


def render(c: Candidate) -> str:
    """The clip as plain text for the model: what a viewer sees and hears, timed from the clip start."""
    head = f"CANDIDATE {c.id} ({c.duration:.1f}s, {'one continuous stretch' if c.kind == 'single' else 'two moments joined'})"
    rows = [head]
    for ln in c.lines:
        if ln.get("cut"):
            rows.append(f"[+{ln['at']:.1f}s] --- CUT TO A DIFFERENT MOMENT ---")
            continue
        stamp = f"[+{ln['at']:.1f}s]"
        if ln["kind"] == "dialogue":
            notes = ", ".join(x for x in (ln["voice"], ln["delivery"]) if x)
            rows.append(f'{stamp} {ln["speaker"]}{f" ({notes})" if notes else ""}: "{ln["text"]}"')
        else:
            label = {"camera": "CAMERA", "action": "ACTION", "sound": "SOUND"}[ln["kind"]]
            rows.append(f"{stamp} {label}{' (already running)' if ln['already_running'] else ''}: {ln['text']}")
    rows.append(f"[+{c.duration:.1f}s] --- CLIP ENDS ---")
    return "\n".join(rows)
