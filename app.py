"""Promo Finder: the Streamlit front end. Run with:  py -m streamlit run app.py"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

from promo_finder.config import ROOT, LLMConfig, RankWeights, load_weights
from promo_finder.parser import parse_folder
from promo_finder.pipeline import RunOptions, promos_csv, run_pipeline
from promo_finder.scorer import ModelRejected

SAMPLE_SCRIPTS = ROOT / "data" / "scripts"
SAMPLE_RESULTS = ROOT / "raw_outputs"  # the processed sample show, full text (local only, not in git)
PUBLIC_SAMPLE = ROOT / "sample_results" / "promos_ranked_public.json"  # same ranking with quoted lines removed (in git)
APP_OUT = ROOT / "outputs" / "app_runs"

MODELS = {
    "gemini": ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"],
    "openai": [],
    "anthropic": ["claude-sonnet-5-5", "claude-opus-5-5"],
}
PROVIDER_LABELS = {"gemini": "Google Gemini", "openai": "OpenAI", "anthropic": "Anthropic Claude"}

HELP = {
    "hook": "What happens in the first 3 seconds of the clip to stop someone scrolling: a slap, a reveal, a shocking line. Scored 0 to 10.",
    "cliffhanger": "How unresolved the moment is where the clip cuts, so the viewer needs to know what happens next. Scored 0 to 10.",
    "standalone": "How well someone who has never seen the show can follow the clip on its own. Scored 0 to 10.",
    "segment": "One continuous stretch of one episode, with its start and end timestamps. Most promos are one segment; some join two moments.",
    "status": "Selected promos are the ones to post. Overlap means it shares screen time with a better promo. Duplicate means it shows the same story moment as a better promo.",
    "key_moment": "The one story event the clip is built around, in the model's words.",
    "checks": "Code-side checks of the model's answer: the quoted hook and cliffhanger lines really appear in the clip, the hook is inside the first 3 seconds and the cliffhanger is in the last 5.",
    "dry_run": "Uses replies already saved from earlier runs and never contacts the model. Clips with no saved reply are left unscored.",
    "episodes_per_call": "How many episodes are scored in one request to the model. More episodes per call means fewer requests, which matters on free tiers that cap requests per day.",
}


def secret(name: str) -> str:
    """A value from Streamlit secrets (deployment) or the environment / .env (local), else empty."""
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # no secrets file: fine
        pass
    import os

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    return os.getenv(name, "")


def rank_help(w: RankWeights) -> str:
    total = w.hook + w.cliffhanger + w.standalone
    return (f"Weighted mix of the three scores, from 0 to 10. Hook counts {w.hook / total:.0%}, "
            f"cliffhanger {w.cliffhanger / total:.0%}, standalone clarity {w.standalone / total:.0%}.")


def fmt_segments(p: dict) -> str:
    return "  +  ".join(f"Episode {s['episode']} · {s['start']} → {s['end']}" for s in p["segments"])


def check_uploads(folder: Path) -> tuple[list, list[str]]:
    """Parse the uploaded files. Returns (episodes that can be used, problems to show)."""
    problems = []
    try:
        episodes = parse_folder(folder)
    except UnicodeDecodeError as exc:
        return [], [f"A file is not UTF-8 text: {exc.reason}. Save the screenplay as plain UTF-8 .txt."]
    usable = []
    for ep in episodes:
        blocks = sum(len(sc.blocks) for sc in ep.scenes)
        if ep.number is None or blocks == 0:
            relevant = [w for w in ep.warnings if "filename" not in w] or ["no timestamped blocks found"]
            why = relevant[0]
            problems.append(f"**{ep.source_file}** is not in the screenplay format ({why}). "
                            "Expected: EPISODE NUMBER header, SCENE blocks, and **CAMERA/ACTION/NAME:** lines with Start/End times.")
        elif ep.duration < 20:
            problems.append(f"**{ep.source_file}** is only {ep.duration:.0f}s long, shorter than the shortest promo (20s). Skipped.")
        else:
            usable.append(ep)
    return usable, problems


def run_on(folder: Path, out: Path, opts: RunOptions, total_calls: int | None = None) -> dict:
    """Run the pipeline with a progress bar. Returns the result, or {"error": message}."""
    lines: list[str] = []
    started = time.time()
    with st.status("Finding promos…", expanded=True) as status:
        bar = st.progress(0.0, text="Reading screenplays…")
        box = st.empty()

        def log(msg: str) -> None:
            lines.append(msg)
            box.code("\n".join(lines[-6:]), language=None)
            m = re.match(r"\[(\d+)/(\d+)\]", msg)
            if m:
                n, total = int(m[1]), int(m[2]) + 1  # +1 for the duplicate check at the end
                done = n if msg.rstrip().endswith(("done", "saved reply")) else n - 1
                elapsed = time.time() - started
                remaining = (elapsed / done * (total - done)) if done else None
                eta = f" · about {remaining / 60:.0f} min left" if remaining and remaining > 90 else (f" · about {remaining:.0f}s left" if remaining else "")
                bar.progress(min(done / total, 0.99), text=f"Scoring with the model: call {min(n, total)} of {total}{eta}")
            elif msg.startswith("[duplicates]"):
                bar.progress(0.97, text="Checking for duplicate moments…")
            elif msg.startswith("Layer 1"):
                bar.progress(0.05, text="Candidate clips found, now scoring with the model…")

        try:
            result = run_pipeline(folder, out, opts, log=log)
        except ModelRejected as exc:
            status.update(label="The model rejected the request", state="error", expanded=True)
            return {"error": f"The model rejected the request. Check the provider, model name and API key. Details: {str(exc)[:300]}"}
        except Exception as exc:  # anything else: show it, do not crash the page
            status.update(label="The run failed", state="error", expanded=True)
            return {"error": f"The run failed: {type(exc).__name__}: {str(exc)[:300]}"}
        if "stopped" in result:
            status.update(label="Stopped", state="error", expanded=True)
        else:
            bar.progress(1.0, text=f"Done in {(time.time() - started) / 60:.1f} min")
            status.update(label="Done", state="complete", expanded=False)
    return result | {"log": lines}


def load_sample() -> dict:
    """The processed sample show. Reads the saved results; never calls a model."""
    ranked = SAMPLE_RESULTS / "promos_ranked.json"
    if ranked.exists():
        return json.loads(ranked.read_text(encoding="utf-8")) | {"source": "sample show, full results"}
    if PUBLIC_SAMPLE.exists():
        return json.loads(PUBLIC_SAMPLE.read_text(encoding="utf-8")) | {"source": "sample show, public copy"}
    # Not fully processed yet: build what we can from the saved replies, in a scratch folder.
    out = APP_OUT / "sample"
    shutil.rmtree(out, ignore_errors=True)
    if (SAMPLE_RESULTS / "llm_raw").exists():
        shutil.copytree(SAMPLE_RESULTS / "llm_raw", out / "llm_raw")
    opts = RunOptions(dry_run=True, cfg=LLMConfig("gemini", "saved replies", "none"))
    return run_on(SAMPLE_SCRIPTS, out, opts) | {"source": "sample (partial, from saved replies)"}


def score_badge(label: str, value: float, help_text: str) -> None:
    st.metric(label, f"{value:.0f}/10", help=help_text)


def render_promo(p: dict, weights: RankWeights) -> None:
    with st.container(border=True):
        head, scores = st.columns([3, 2])
        with head:
            if p["status"] == "selected":
                st.markdown(f"### #{p['rank']} &nbsp; <span style='font-size:0.7em;color:gray'>Rank score {p['final_score']:.1f}</span>",
                            unsafe_allow_html=True, help=rank_help(weights))
            else:
                st.markdown(f"### {p['status'].capitalize()} of {p['replaced_by']} &nbsp; "
                            f"<span style='font-size:0.7em;color:gray'>Rank score {p['final_score']:.1f}</span>",
                            unsafe_allow_html=True, help=HELP["status"])
            st.markdown(f"**{fmt_segments(p)}** &nbsp;·&nbsp; {p['duration_seconds']:.0f}s", help=HELP["segment"])
            st.caption(p.get("key_moment", ""), help=HELP["key_moment"])
        with scores:
            a, b, c = st.columns(3)
            with a:
                score_badge("Hook", p["hook_score"], HELP["hook"])
            with b:
                score_badge("Cliffhanger", p["cliffhanger_score"], HELP["cliffhanger"])
            with c:
                score_badge("Standalone", p["standalone_score"], HELP["standalone"])

        if "hook_line" in p:
            st.markdown(f"**Hook** &nbsp; {p['hook_line']}", help=HELP["hook"])
            st.markdown(f"**Cliffhanger** &nbsp; {p['cliffhanger_line']}", help=HELP["cliffhanger"])
            st.markdown(f"**Why it works** &nbsp; {p['why_it_works']}")
        failed = [k for k, v in p.get("checks", {}).items() if not v]
        if failed:
            st.caption("⚠ Check failed: " + ", ".join(k.replace("_", " ") for k in failed), help=HELP["checks"])


def main() -> None:
    st.set_page_config(page_title="Promo Finder", page_icon="🎬", layout="wide")
    st.title("Promo Finder")
    st.caption("Reads microdrama screenplays and finds the best 20 to 60 second promo clips, with exact start and end timestamps. "
               "Each clip opens on a hook, ends on a cliffhanger and should make sense to someone who has never seen the show.")

    env_weights = load_weights()
    result = st.session_state.get("result")

    with st.container(border=True):
        c1, c2, c3 = st.columns([5, 4, 2])
        with c1:
            st.markdown("**1 · Screenplays**")
            uploads = st.file_uploader("Upload screenplay .txt files, one per episode", type="txt", accept_multiple_files=True,
                                       help="The timestamped screenplay format: scene headings, then CAMERA, ACTION, SOUND FX and dialogue blocks with start and end times.")
            can_sample = (SAMPLE_RESULTS / "promos_ranked.json").exists() or PUBLIC_SAMPLE.exists() or (SAMPLE_SCRIPTS.exists() and (SAMPLE_RESULTS / "llm_raw").exists())
            if st.button("Or open the sample show (50 episodes, already processed)", disabled=not can_sample,
                         help="Shows results already computed for the sample show. Makes no API calls."):
                st.session_state["result"] = load_sample()
                st.rerun()
        with c2:
            st.markdown("**2 · Model**")
            saved_provider, saved_model, saved_key = secret("LLM_PROVIDER").lower(), secret("LLM_MODEL"), secret("LLM_API_KEY")
            providers = list(MODELS)
            provider = st.selectbox("Provider", providers, index=providers.index(saved_provider) if saved_provider in providers else 0,
                                    format_func=PROVIDER_LABELS.get, help="Which company's model scores the clips. The code is the same for all three.")
            options = MODELS[provider] + ["Other…"]
            preset = options.index(saved_model) if saved_model in options else (len(options) - 1 if saved_model and provider == saved_provider else 0)
            choice = st.selectbox("Model", options, index=preset, help="Model name exactly as the provider calls it.") if MODELS[provider] else "Other…"
            model = st.text_input("Model name", value=saved_model if provider == saved_provider else "", placeholder="type the model name",
                                  label_visibility="collapsed") if choice == "Other…" else choice
            api_key = st.text_input("API key", value=saved_key if provider == saved_provider else "", type="password",
                                    help="Used only for this run. Prefilled from your .env or Streamlit secrets if set; never shown or stored.")
        with c3:
            st.markdown("**3 · Run**")
            run_clicked = st.button("Find promos", type="primary", use_container_width=True,
                                    help="Scores the uploaded screenplays with the chosen model. About one request per 5 episodes.")
            with st.expander("Advanced"):
                dry_run = st.checkbox("Dry run (no API calls)", value=False, help=HELP["dry_run"])
                per_call = st.number_input("Episodes per call", 1, 10, 5, help=HELP["episodes_per_call"])
                st.caption("Rank score weights")
                w_hook = st.number_input("Hook", 0.0, 10.0, float(env_weights.hook), 0.1, help=HELP["hook"])
                w_cliff = st.number_input("Cliffhanger", 0.0, 10.0, float(env_weights.cliffhanger), 0.1, help=HELP["cliffhanger"])
                w_alone = st.number_input("Standalone", 0.0, 10.0, float(env_weights.standalone), 0.1, help=HELP["standalone"])

    weights = RankWeights(w_hook, w_cliff, w_alone) if (w_hook + w_cliff + w_alone) > 0 else env_weights

    if run_clicked:
        if not uploads:
            st.error("Upload at least one screenplay .txt file first, or open the sample show.")
        elif not model.strip():
            st.error("Enter a model name.")
        elif not api_key.strip() and not dry_run:
            st.error("Paste an API key, or tick Dry run under Advanced.")
        else:
            folder = Path(tempfile.mkdtemp(prefix="promo_in_"))
            for f in uploads:
                (folder / f.name).write_bytes(f.getvalue())
            usable, problems = check_uploads(folder)
            for msg in problems:
                st.error(msg)
            if not usable:
                st.stop()
            out = APP_OUT / datetime.now().strftime("%Y%m%d-%H%M%S")
            cfg = LLMConfig(provider, model.strip(), api_key.strip() or "none")
            opts = RunOptions(dry_run=dry_run, episodes_per_call=int(per_call), cfg=cfg, weights=weights)
            result = run_on(folder, out, opts)
            if "error" in result:
                st.error(result["error"])
            else:
                st.session_state["result"] = result | {"source": f"{len(usable)} uploaded file(s)"}
                st.rerun()

    if not result:
        st.info("Upload screenplays and click **Find promos**, or open the sample show to see what the results look like.")
        return

    if "stopped" in result:
        st.error(f"The run stopped before finishing: {result['stopped']}")
        return
    if "error" in result:
        st.error(result["error"])
        return

    promos = result["promos"]
    selected = [p for p in promos if p["status"] == "selected"]
    st.subheader("Ranked promos")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Promos selected", len(selected), help=HELP["status"])
    m2.metric("Clips scored", result.get("scored", len(promos)), help="Candidate clips the model scored. Unscored ones had no saved reply in a dry run.")
    m3.metric("Episodes", result.get("episodes", "–"))
    m4.metric("Run time", f"{result.get('total_seconds', 0) / 60:.1f} min")
    st.caption(f"Source: {result.get('source', 'run')} · Model: {result.get('model', '–')} · Rank score = "
               + rank_help(weights).split(". ", 1)[1])
    if not promos:
        st.warning("No clips were scored, so there is nothing to rank." + (" Untick Dry run under Advanced to call the model." if result.get("dry_run") else ""))
        return
    if result.get("unscored"):
        st.warning(f"{result['unscored']} candidate clips were not scored ({'dry run' if result.get('dry_run') else 'model calls failed'}).")
    if result.get("duplicate_check_error"):
        st.warning("The duplicate check did not run, so no promos are marked as duplicates.")
    if result.get("note"):
        st.info(result["note"])

    d1, d2, d3, d4, _ = st.columns([1, 1, 2, 2, 2])
    d1.download_button("Download CSV", promos_csv(promos), "promos_ranked.csv", "text/csv", use_container_width=True)
    d2.download_button("Download JSON", json.dumps(result, indent=2, ensure_ascii=False), "promos_ranked.json", "application/json",
                       use_container_width=True)
    show_all = d3.toggle("Show overlaps and duplicates too", value=False, help=HELP["status"])
    limit = d4.number_input("Show top", 1, max(len(promos), 1), min(20, max(len(promos), 1)), help="How many promos to list on the page. The downloads always contain all of them.")

    for p in (promos if show_all else selected)[: int(limit)]:
        render_promo(p, weights)

    with st.expander("What the terms mean"):
        st.markdown(f"""
- **Hook**: {HELP['hook']}
- **Cliffhanger**: {HELP['cliffhanger']}
- **Standalone clarity**: {HELP['standalone']}
- **Rank score**: {rank_help(weights)}
- **Segment**: {HELP['segment']}
- **Selected / overlap / duplicate**: {HELP['status']}
- **Checks**: {HELP['checks']}
""")


main()
