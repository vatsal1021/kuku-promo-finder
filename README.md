# Promo Finder

Reads microdrama screenplays (one timestamped .txt per episode) and finds the best 20 to 60 second promo clips.
Code rules propose candidate windows on real shot boundaries; a language model scores each one on hook, cliffhanger and standalone clarity.
Output is a ranked list with exact start and end timestamps, the hook line, the cliffhanger line and one line on why it works.

Built for the Kuku AI Generalist assignment, Problem 1.

## Run locally

1. Install Python 3.11 or newer, then install the packages:

   ```bash
   py -m pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and paste your API key into `LLM_API_KEY`.

3. Put the screenplay .txt files in `data/scripts/` (one file per episode).

4. Start the app:

   ```bash
   py -m streamlit run app.py
   ```

   Upload screenplays, pick the provider and model, paste the key, click **Find promos**. Or run from the command line:

   ```bash
   py -m promo_finder.pipeline data/scripts --out raw_outputs
   ```

Useful flags: `--episodes 1-5` (trial on a few episodes), `--skip-llm` (rules only, no key needed), `--dry-run` (reuse saved model replies, no API calls), `--episodes-per-call 5` (fewer requests on free tiers).

## Swap the model

Everything about the model is in `.env`:

```
LLM_PROVIDER=gemini        # gemini | openai | anthropic
LLM_MODEL=gemini-3.8-flash # the model name as the provider calls it
LLM_API_KEY=...
LLM_BASE_URL=              # optional custom endpoint for openai / anthropic
```

Change the three values and run again; nothing else changes. The one place that talks to a model is `promo_finder/llm.py`, so a new provider is one more branch there. The app also lets you pick provider, model and key per run. The prompts are plain text in `prompts/` and the ranking weights (`RANK_WEIGHT_*`) are in `.env` too.

On the Gemini free tier the binding limit is requests per day (20 per model when this was built), and failed attempts count. Scoring 50 episodes takes 13 requests at 5 episodes per call.

## Deploy on Streamlit Community Cloud

Copy `.streamlit/secrets.toml.example` into the app's **Secrets** box in the Streamlit Cloud settings and fill in the key. The app reads `LLM_PROVIDER`, `LLM_MODEL` and `LLM_API_KEY` from secrets and prefills the form. `.streamlit/secrets.toml` and `.env` are git-ignored, so keys never end up in the repo.

## Where the outputs go

`raw_outputs/` (command line) or `outputs/app_runs/<timestamp>/` (app), unedited:

| File | What it is |
|---|---|
| `promos_ranked.json`, `promos_ranked.csv` | every scored clip, ranked, with status `selected`, `overlap` or `duplicate` |
| `episodes/episode-NNN.json` | one file per episode: its candidate clips with the script lines and the model's result |
| `llm_raw/` | every prompt sent and every reply exactly as it came back, including rejected ones |
| `candidates.json` | the rule-layer candidates before scoring |
| `run_summary.json` | time taken, API calls, failed calls, tokens |

## Layout

```
app.py                      Streamlit front end
promo_finder/parser.py      screenplay .txt -> episodes, scenes, timestamped blocks
promo_finder/candidates.py  layer 1: rule-based candidate windows (cue words in cues.py)
promo_finder/scorer.py      layer 2: model scoring, JSON validation, duplicate grouping
promo_finder/ranking.py     weighted rank score, overlap and duplicate handling
promo_finder/pipeline.py    runs everything, writes the outputs
promo_finder/llm.py         one complete() for Gemini, OpenAI, Anthropic
prompts/                    the two prompts, editable
failures.md                 where the tool picks badly, with episode and timestamps
```

## Not included

The screenplays in `data/scripts/` are Kuku's confidential input pack and are not in this repo, and neither are the run outputs, which quote them. To rerun, place the files in `data/scripts/`. The parser expects the input pack format: an `EPISODE NUMBER` header, `SCENE` blocks, and `**CAMERA:**`, `**ACTION:**`, `**SOUND FX:**` or `**NAME (delivery):**` tags each followed by a `Start: (MM:SS.ss) | End: (MM:SS.ss)` line.
