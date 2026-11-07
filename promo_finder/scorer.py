"""Layer 2: the model scores each candidate on hook, cliffhanger and standalone clarity.

The prompt lives in prompts/score_candidates.md. The model returns strict JSON, which is
validated here, and the lines it quotes are checked against the clip.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from .candidates import HOOK_WINDOW, Candidate, render
from .config import ROOT
from .llm import complete

PROMPT_FILE = ROOT / "prompts" / "score_candidates.md"
SCORES = ("hook_score", "cliffhanger_score", "standalone_score")
TEXTS = ("hook_line", "cliffhanger_line", "why_it_works", "key_moment")
GROUP_PROMPT_FILE = ROOT / "prompts" / "group_duplicates.md"
CLIFF_WINDOW = 5.0  # the quoted cliffhanger must end within this many seconds of the cut
MAX_QUOTA_WAIT = 300  # if the provider says to wait longer than this, the quota is gone for now: stop


class ModelRejected(RuntimeError):
    """Wrong API key, model name or request. Retrying cannot help."""


class QuotaExhausted(RuntimeError):
    """The provider's quota is used up (for example a per-day limit). Retrying soon cannot help."""


def _retry_after(message: str) -> float | None:
    """Seconds the provider asked us to wait, read from a rate-limit error message."""
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", message)
    if m:
        return int(m[1] or 0) * 3600 + int(m[2] or 0) * 60 + float(m[3])
    m = re.search(r"retryDelay'?:\s*'?(\d+)s", message)
    return float(m[1]) if m else None


def build_prompt(batch: list[Candidate], template: str | None = None) -> str:
    template = template if template is not None else PROMPT_FILE.read_text(encoding="utf-8")
    if "{{CANDIDATES}}" not in template:
        raise ValueError(f"{PROMPT_FILE} must contain the placeholder {{{{CANDIDATES}}}}")
    return template.replace("{{CANDIDATES}}", "\n\n".join(render(c) for c in batch))


def parse_response(text: str, expected_ids: list[str]) -> dict[str, dict]:
    """Turn the model's reply into {candidate id: scores}. Raises ValueError if it is not usable."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("reply contains no JSON object")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"reply is not valid JSON: {exc}") from exc
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        raise ValueError('reply has no "results" list')

    out: dict[str, dict] = {}
    for item in results:
        if not isinstance(item, dict) or item.get("id") not in expected_ids:
            raise ValueError(f"unexpected entry or id: {str(item)[:80]}")
        row = {}
        for key in SCORES:
            value = item.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 10:
                raise ValueError(f"{item['id']}: {key} must be a number from 0 to 10, got {value!r}")
            row[key] = round(float(value), 1)
        for key in TEXTS:
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{item['id']}: {key} is missing or empty")
            row[key] = value.strip()
        out[item["id"]] = row
    missing = [i for i in expected_ids if i not in out]
    if missing:
        raise ValueError(f"reply is missing candidates: {missing}")
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _locate(c: Candidate, quoted: str) -> list[dict]:
    """Clip lines whose text contains the quoted line (or the other way round)."""
    # The model often copies the speaker label too: NAME (Cold): "the line". Match on the spoken part.
    inner = re.search(r'["“](.+)["”]', quoted)
    wanted = {q for q in (_norm(quoted), _norm(inner[1]) if inner else "") if len(q) >= 3}
    hits = []
    for ln in c.lines:
        if ln.get("cut"):
            continue
        t = _norm(ln["text"])
        if any(q in t or (len(t) >= 8 and t in q) for q in wanted):
            hits.append(ln)
    return hits


def check_quotes(c: Candidate, row: dict) -> dict:
    """Code-side check of the model's answer: are the quoted lines real, and are they where they should be?"""
    hook, cliff = _locate(c, row["hook_line"]), _locate(c, row["cliffhanger_line"])
    return {
        "hook_line_found": bool(hook),
        "hook_in_first_3s": any(h["at"] < HOOK_WINDOW for h in hook),
        "cliffhanger_line_found": bool(cliff),
        "cliffhanger_at_end": any(c.duration - h["until"] <= CLIFF_WINDOW for h in cliff),
    }


def make_batches(candidates: list[Candidate], episodes_per_call: int = 1, stitched_per_call: int = 5) -> list[tuple[str, list[Candidate]]]:
    """Group candidates into model calls: single-stretch ones by episode, then stitched ones a few at a time.

    episodes_per_call above 1 puts several episodes in one call, which uses fewer requests
    (free tiers cap requests per day) at the price of a longer prompt per call.
    """
    by_episode: dict[int, list[Candidate]] = {}
    for c in candidates:
        if c.kind == "single":
            by_episode.setdefault(c.segments[0].episode, []).append(c)
    numbers = sorted(by_episode)
    batches: dict[str, list[Candidate]] = {}
    for i in range(0, len(numbers), episodes_per_call):
        chunk = numbers[i : i + episodes_per_call]
        name = f"ep-{chunk[0]:03d}" if len(chunk) == 1 else f"ep-{chunk[0]:03d}-{chunk[-1]:03d}"
        batches[name] = [c for n in chunk for c in by_episode[n]]
    stitched = [c for c in candidates if c.kind == "stitched"]
    for i in range(0, len(stitched), stitched_per_call):
        batches[f"stitched-{i // stitched_per_call + 1:02d}"] = stitched[i : i + stitched_per_call]
    return list(batches.items())


def _ask(name: str, prompt: str, parse, raw_dir: Path, label: str, delay: float, retries: int, force: bool, log,
         cfg=None, dry_run: bool = False):
    """One model call with caching and retries. Returns (parsed reply or None, last error).

    The raw reply is saved in raw_dir. A rerun reuses it when the prompt is unchanged,
    so a crash or rate limit does not cost the calls already made.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:10]
    raw_file = raw_dir / f"{name}-{digest}.json"

    if raw_file.exists() and not force:
        try:
            parsed = parse(json.loads(raw_file.read_text(encoding="utf-8"))["reply"])
            log(f"{label} {name}: reused saved reply")
            return parsed, ""
        except (ValueError, KeyError):
            pass
    if dry_run:
        log(f"{label} {name}: no saved reply (dry run, not calling the model)")
        return None, "dry run: no saved reply"

    error = ""
    for attempt in range(1, retries + 1):
        reply = ""
        try:
            reply = complete(prompt, json_mode=True, cfg=cfg)
            parsed = parse(reply)
            raw_file.write_text(json.dumps({"batch": name, "prompt": prompt, "reply": reply}, indent=2, ensure_ascii=False), encoding="utf-8")
            log(f"{label} {name}: done")
            time.sleep(delay)
            return parsed, ""
        except Exception as exc:  # network, rate limit or an unusable reply: wait and retry
            error = f"{type(exc).__name__}: {str(exc)[:300]}"
            status = next((v for v in (getattr(exc, "status_code", None), getattr(exc, "code", None)) if isinstance(v, int)), None)
            if status in (400, 401, 403, 404):  # wrong model name or key: retrying cannot help
                raise ModelRejected(f"The model rejected the request (HTTP {status}). Check the provider, model name and API key. {error}") from exc
            asked = _retry_after(str(exc)) if status == 429 else None
            if status == 429 and (("per day" in str(exc)) or (asked or 0) > MAX_QUOTA_WAIT):
                detail = re.search(r"limit: \d+, model: [\w.-]+", str(exc))
                raise QuotaExhausted(
                    f"Quota used up ({detail[0] if detail else 'see provider message'}). "
                    f"Provider says retry in {(asked or 0) / 3600:.1f} hours. Replies saved so far are kept; rerun later to continue."
                ) from exc
            if reply:  # keep unusable replies too, for the quality write-up
                (raw_dir / f"{name}-{digest}-failed-{attempt}.json").write_text(
                    json.dumps({"batch": name, "error": error, "reply": reply}, indent=2, ensure_ascii=False), encoding="utf-8")
            wait = delay + 15 * 2 ** (attempt - 1)
            if asked:  # a per-minute limit: wait as long as the provider asked, plus a little
                wait = max(wait, asked + 2)
            log(f"{label} {name}: attempt {attempt} failed ({error[:120]})" + (f", waiting {wait:.0f}s" if attempt < retries else ""))
            if attempt < retries:
                time.sleep(wait)
    return None, error


def score_candidates(
    candidates: list[Candidate],
    raw_dir: Path,
    delay: float = 5.0,
    retries: int = 3,
    force: bool = False,
    log=print,
    episodes_per_call: int = 1,
    stitched_per_call: int = 5,
    cfg=None,
    dry_run: bool = False,
) -> tuple[dict[str, dict], list[dict]]:
    """Score every candidate. Returns ({id: scores}, [failures])."""
    template = PROMPT_FILE.read_text(encoding="utf-8")
    scores: dict[str, dict] = {}
    failures: list[dict] = []
    batches = make_batches(candidates, episodes_per_call, stitched_per_call)
    for n, (name, batch) in enumerate(batches, 1):
        ids = [c.id for c in batch]
        parsed, error = _ask(name, build_prompt(batch, template), lambda reply: parse_response(reply, ids),
                             raw_dir, f"[{n}/{len(batches)}]", delay, retries, force, log, cfg, dry_run)
        if parsed is None:
            failures.append({"batch": name, "candidates": ids, "error": error})
            continue
        for c in batch:
            scores[c.id] = parsed[c.id] | {"checks": check_quotes(c, parsed[c.id])}
    return scores, failures


def parse_groups(text: str, known_ids: set[str]) -> list[list[str]]:
    """Turn the model's reply into groups of duplicate ids. Raises ValueError if it is not usable."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("reply contains no JSON object")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"reply is not valid JSON: {exc}") from exc
    groups = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(groups, list):
        raise ValueError('reply has no "groups" list')
    seen: set[str] = set()
    out = []
    for group in groups:
        if not isinstance(group, list) or len(group) < 2 or not all(isinstance(i, str) for i in group):
            raise ValueError(f"each group must be a list of two or more ids, got {str(group)[:80]}")
        unknown = [i for i in group if i not in known_ids]
        if unknown:
            raise ValueError(f"unknown ids in a group: {unknown}")
        if seen & set(group):
            raise ValueError(f"ids appear in more than one group: {sorted(seen & set(group))}")
        seen |= set(group)
        out.append(list(dict.fromkeys(group)))
    return out


def group_duplicates(
    candidates: list[Candidate],
    scores: dict[str, dict],
    raw_dir: Path,
    delay: float = 5.0,
    retries: int = 3,
    force: bool = False,
    log=print,
    cfg=None,
    dry_run: bool = False,
) -> tuple[list[list[str]], str]:
    """Ask the model which scored promos show the same story beat. Returns (groups, error)."""
    rows = []
    for c in candidates:
        if c.id not in scores:
            continue
        s = scores[c.id]
        where = " + ".join(f"episode {seg.episode}" for seg in c.segments)
        rows.append(f"{c.id} | {where} | key moment: {s['key_moment']} | opens on: {s['hook_line']} | ends on: {s['cliffhanger_line']}")
    if len(rows) < 2:
        return [], ""
    template = GROUP_PROMPT_FILE.read_text(encoding="utf-8")
    if "{{PROMOS}}" not in template:
        raise ValueError(f"{GROUP_PROMPT_FILE} must contain the placeholder {{{{PROMOS}}}}")
    known = set(scores)
    parsed, error = _ask("duplicates", template.replace("{{PROMOS}}", "\n".join(rows)),
                         lambda reply: parse_groups(reply, known), raw_dir, "[duplicates]", delay, retries, force, log, cfg, dry_run)
    return (parsed or []), error
