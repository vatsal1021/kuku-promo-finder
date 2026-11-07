"""Screenplay parser: turns the timestamped .txt screenplays into structured data.

Standard library only, no model calls. Run it on a folder to parse and validate:

    py -m promo_finder.parser data/scripts --out data/parsed/episodes.json

Every timestamp is converted to seconds from the start of its episode.
Anything the parser does not recognise is reported as a warning, never dropped silently.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Tags that are not spoken lines. Every other **TAG:** is treated as dialogue.
NON_DIALOGUE = {"CAMERA": "camera", "ACTION": "action", "SOUND FX": "sound"}
# Parentheticals that describe how a line is heard, not how it is delivered.
VOICE_FLAGS = {"O.S.", "V.O.", "O.C."}
TOLERANCE = 0.05  # seconds of slack when comparing timestamps

CLOCK = r"(\d+):(\d+(?:\.\d+)?)"
RE_HEADER = re.compile(r"^(EPISODE NUMBER|EPISODE LOGLINE|CONTINUITY NOTES):\s*(.*)$")
RE_SCENE = re.compile(r"^SCENE\s+(\d+)\s*$")
RE_SCENE_FIELD = re.compile(r"^Scene (heading|start|end):\s*(.*)$", re.IGNORECASE)
RE_TAG = re.compile(r"^\*\*(.+?):?\*\*:?\s*$")
RE_TIMES = re.compile(rf"^Start:\s*\({CLOCK}\)\s*\|\s*End:\s*\({CLOCK}\)\s*$")
RE_FILENAME = re.compile(r"^episode-(\d+)-Episode (\d+)\.txt$")


@dataclass
class Block:
    """One timestamped camera move, action, sound effect or line of dialogue."""

    kind: str  # camera | action | sound | dialogue
    start: float
    end: float
    text: str
    speaker: str | None = None  # dialogue only, as written in the script
    delivery: str | None = None  # dialogue only, e.g. "Cold, Commanding"
    voice: str | None = None  # dialogue only, e.g. "O.S." or "V.O."
    line_no: int = 0  # line of the tag in the source file


@dataclass
class Scene:
    number: int
    heading: str = ""
    start: float | None = None
    end: float | None = None
    blocks: list[Block] = field(default_factory=list)


@dataclass
class Episode:
    number: int | None
    source_file: str
    episode_id: str | None = None  # the numeric id in the filename
    logline: str = ""
    continuity: str = ""
    duration: float = 0.0
    scenes: list[Scene] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def to_seconds(minutes: str, seconds: str) -> float:
    return round(int(minutes) * 60 + float(seconds), 2)


def fmt_time(seconds: float) -> str:
    """Seconds back to the script's MM:SS.ss form."""
    return f"{int(seconds // 60):02d}:{seconds % 60:05.2f}"


def _split_tag(tag: str) -> tuple[str, str | None, str | None]:
    """'CATHERINE (O.S.) (Derisive, Projecting)' -> speaker, delivery, voice."""
    speaker = tag.split("(", 1)[0].strip()
    delivery, voice = [], []
    for part in re.findall(r"\(([^)]*)\)", tag):
        (voice if part.strip().upper() in VOICE_FLAGS else delivery).append(part.strip())
    return speaker, ", ".join(delivery) or None, ", ".join(voice) or None


def parse_episode(path: Path) -> Episode:
    ep = Episode(number=None, source_file=path.name)
    warn = ep.warnings.append

    m = RE_FILENAME.match(path.name)
    file_number = int(m[1]) if m else None
    if m:
        ep.episode_id = m[2]
    else:
        warn(f"filename does not match 'episode-NNN-Episode ID.txt'")

    lines = path.read_text(encoding="utf-8-sig").splitlines()
    scene: Scene | None = None
    block: Block | None = None  # block currently collecting text
    pending_tag: tuple[str, int] | None = None  # tag seen, waiting for its Start/End line
    saw_start = saw_end = False

    def close_block() -> None:
        nonlocal block
        if block is None:
            return
        block.text = block.text.strip()
        if block.kind == "dialogue":
            if len(block.text) >= 2 and block.text[0] in '"“' and block.text[-1] in '"”':
                block.text = block.text[1:-1].strip()
            else:
                warn(f"line {block.line_no}: dialogue is not wrapped in quotes")
        if not block.text:
            warn(f"line {block.line_no}: block has no text")
        block = None

    for no, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line:
            close_block()
            continue
        if line == "--- SCRIPT START ---":
            saw_start = True
            continue
        if line == "--- SCRIPT END ---":
            close_block()
            saw_end = True
            continue
        if line.lower() == "actions and dialogue:":
            if line != "Actions and dialogue:":
                warn(f"line {no}: written as '{line}' (expected 'Actions and dialogue:')")
            continue

        if not saw_start and (m := RE_HEADER.match(line)):
            key, value = m[1], m[2].strip()
            if key == "EPISODE NUMBER":
                num = re.search(r"\d+", value)
                ep.number = int(num[0]) if num else None
            elif key == "EPISODE LOGLINE":
                ep.logline = value
            else:
                ep.continuity = value
            continue

        if m := RE_SCENE.match(line):
            close_block()
            scene = Scene(number=int(m[1]))
            ep.scenes.append(scene)
            continue

        if (m := RE_SCENE_FIELD.match(line)) and scene is not None and not scene.blocks:
            key, value = m[1].lower(), m[2].strip()
            if line[:6] != "Scene ":
                warn(f"line {no}: scene field written as '{line.split(':')[0]}' (expected 'Scene {key}')")
            if key == "heading":
                scene.heading = value
            else:
                t = re.fullmatch(CLOCK, value)
                if t:
                    setattr(scene, key, to_seconds(t[1], t[2]))
                else:
                    warn(f"line {no}: cannot read scene {key} time '{value}'")
            continue

        if m := RE_TAG.match(line):
            close_block()
            if pending_tag:
                warn(f"line {pending_tag[1]}: tag '{pending_tag[0]}' has no Start/End line")
            pending_tag = (m[1].strip().rstrip(":").strip(), no)
            continue

        if m := RE_TIMES.match(line):
            if pending_tag is None:
                warn(f"line {no}: Start/End line with no tag above it")
                continue
            if scene is None:
                warn(f"line {no}: block appears before any SCENE header")
                scene = Scene(number=0)
                ep.scenes.append(scene)
            tag, tag_line = pending_tag
            pending_tag = None
            start, end = to_seconds(m[1], m[2]), to_seconds(m[3], m[4])
            if tag.upper() in NON_DIALOGUE:
                block = Block(NON_DIALOGUE[tag.upper()], start, end, "", line_no=tag_line)
            else:
                speaker, delivery, voice = _split_tag(tag)
                block = Block("dialogue", start, end, "", speaker, delivery, voice, tag_line)
            scene.blocks.append(block)
            continue

        if block is not None:  # body text of the current block
            block.text += (" " if block.text else "") + line
            continue

        warn(f"line {no}: unrecognised line: {line[:80]}")

    close_block()
    if pending_tag:
        warn(f"line {pending_tag[1]}: tag '{pending_tag[0]}' has no Start/End line")
    _validate(ep, file_number, saw_start, saw_end)
    return ep


def _validate(ep: Episode, file_number: int | None, saw_start: bool, saw_end: bool) -> None:
    warn = ep.warnings.append
    if ep.number is None:
        warn("EPISODE NUMBER missing or unreadable")
    elif file_number is not None and ep.number != file_number:
        warn(f"header says episode {ep.number} but filename says {file_number}")
    if not ep.logline:
        warn("EPISODE LOGLINE missing")
    if not ep.continuity:
        warn("CONTINUITY NOTES missing")
    if not saw_start:
        warn("'--- SCRIPT START ---' marker missing")
    if not saw_end:
        warn("'--- SCRIPT END ---' marker missing")
    if not ep.scenes:
        warn("no scenes found")
        return

    prev_end = 0.0
    for i, sc in enumerate(ep.scenes, 1):
        where = f"scene {sc.number}"
        if sc.number != i:
            warn(f"{where}: out of sequence (expected scene {i})")
        if not sc.heading:
            warn(f"{where}: heading missing")
        if not sc.blocks:
            warn(f"{where}: has no blocks")
            continue
        first, last = min(b.start for b in sc.blocks), max(b.end for b in sc.blocks)
        if sc.start is None or sc.end is None:
            warn(f"{where}: scene start/end missing, filled in from its blocks")
            sc.start = first if sc.start is None else sc.start
            sc.end = last if sc.end is None else sc.end
        if abs(sc.start - prev_end) > TOLERANCE:
            warn(f"{where}: starts at {fmt_time(sc.start)} but previous scene ended at {fmt_time(prev_end)}")
        if first < sc.start - TOLERANCE or last > sc.end + TOLERANCE:
            warn(f"{where}: blocks run {fmt_time(first)}-{fmt_time(last)}, outside scene {fmt_time(sc.start)}-{fmt_time(sc.end)}")
        if sc.end - last > 3:
            warn(f"{where}: last block ends {fmt_time(last)}, {sc.end - last:.1f}s before scene end {fmt_time(sc.end)}")
        for b in sc.blocks:
            if b.end < b.start:
                warn(f"line {b.line_no}: block ends before it starts")
            elif b.end == b.start:
                warn(f"line {b.line_no}: block has zero length")
        for kind in ("dialogue", "camera"):  # same-kind blocks should not overlap much
            same = sorted((b for b in sc.blocks if b.kind == kind), key=lambda b: b.start)
            for a, b in zip(same, same[1:]):
                if a.end - b.start > 0.5:
                    warn(f"line {b.line_no}: {kind} overlaps the previous {kind} by {a.end - b.start:.2f}s")
        prev_end = sc.end
    ep.duration = max(sc.end or 0.0 for sc in ep.scenes)


def parse_folder(folder: Path) -> list[Episode]:
    files = sorted(Path(folder).glob("*.txt"))
    episodes = [parse_episode(f) for f in files]
    episodes.sort(key=lambda e: (e.number is None, e.number or 0, e.source_file))
    return episodes


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse and validate screenplay .txt files.")
    ap.add_argument("folder", type=Path, help="folder containing the episode .txt files")
    ap.add_argument("--out", type=Path, help="write the parsed episodes to this JSON file")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    episodes = parse_folder(args.folder)
    if not episodes:
        print(f"No .txt files found in {args.folder}")
        return 1

    blocks = [b for e in episodes for s in e.scenes for b in s.blocks]
    counts = {k: sum(b.kind == k for b in blocks) for k in ("camera", "action", "sound", "dialogue")}
    print(f"Parsed {len(episodes)} files: {sum(len(e.scenes) for e in episodes)} scenes, {len(blocks)} blocks")
    print("  " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    print(f"  total runtime {sum(e.duration for e in episodes) / 60:.1f} min")

    numbers = [e.number for e in episodes if e.number is not None]
    missing = sorted(set(range(1, max(numbers) + 1)) - set(numbers)) if numbers else []
    dupes = sorted({n for n in numbers if numbers.count(n) > 1})
    if missing:
        print(f"  MISSING episode numbers: {missing}")
    if dupes:
        print(f"  DUPLICATE episode numbers: {dupes}")

    flagged = [e for e in episodes if e.warnings]
    print(f"\n{len(episodes) - len(flagged)} files clean, {len(flagged)} with warnings")
    for e in flagged:
        print(f"\n{e.source_file}")
        for w in e.warnings:
            print(f"  - {w}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps([asdict(e) for e in episodes], indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
