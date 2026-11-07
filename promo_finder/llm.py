"""One function, three providers. The rest of the code only ever calls complete()."""

from __future__ import annotations

from .config import LLMConfig, load_config

MAX_TOKENS = 8192

# Running totals for this process, so a run can report its cost.
# output_tokens includes thinking_tokens where the provider reports them.
USAGE = {"calls": 0, "failed_calls": 0, "input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0}


def _count(input_tokens, output_tokens, thinking_tokens=0) -> None:
    USAGE["input_tokens"] += input_tokens or 0
    USAGE["output_tokens"] += (output_tokens or 0) + (thinking_tokens or 0)
    USAGE["thinking_tokens"] += thinking_tokens or 0


def complete(prompt: str, system: str = "", cfg: LLMConfig | None = None, json_mode: bool = False) -> str:
    """Send one prompt to the configured model and return its text reply.

    json_mode asks the provider to return JSON where it has a switch for that
    (Gemini, OpenAI). Anthropic has none here, so the prompt itself must ask for JSON.
    """
    cfg = cfg or load_config()
    USAGE["calls"] += 1
    try:
        return _send(prompt, system, cfg, json_mode)
    except Exception:
        USAGE["failed_calls"] += 1
        raise


def _send(prompt: str, system: str, cfg: LLMConfig, json_mode: bool) -> str:
    if cfg.provider == "gemini":
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=cfg.api_key)
        resp = client.models.generate_content(
            model=cfg.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system or None,
                response_mime_type="application/json" if json_mode else None,
            ),
        )
        if resp.usage_metadata:
            m = resp.usage_metadata
            _count(m.prompt_token_count, m.candidates_token_count, m.thoughts_token_count)
        return resp.text or ""

    if cfg.provider == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        extra = {"response_format": {"type": "json_object"}} if json_mode else {}
        resp = client.chat.completions.create(model=cfg.model, messages=messages, **extra)
        if resp.usage:
            _count(resp.usage.prompt_tokens, resp.usage.completion_tokens)
        return resp.choices[0].message.content or ""

    if cfg.provider == "anthropic":
        from anthropic import Anthropic

        client = Anthropic(api_key=cfg.api_key, base_url=cfg.base_url)
        kwargs = {"system": system} if system else {}
        resp = client.messages.create(
            model=cfg.model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        _count(resp.usage.input_tokens, resp.usage.output_tokens)
        return "".join(part.text for part in resp.content if part.type == "text")

    raise ValueError(f"Unknown provider '{cfg.provider}'")
