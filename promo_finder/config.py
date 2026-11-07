"""Model settings. Everything is read from the .env file in the project root.

To swap the model, edit .env (copy .env.example first). Nothing else needs to change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
PROVIDERS = ("gemini", "openai", "anthropic")


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    api_key: str
    base_url: str | None = None  # optional: a custom endpoint for openai / anthropic


@dataclass(frozen=True)
class RankWeights:
    """How much each model score counts in the final ranking. Only the proportions matter."""

    hook: float = 0.5
    cliffhanger: float = 0.3
    standalone: float = 0.2


def load_weights() -> RankWeights:
    load_dotenv(ROOT / ".env")
    defaults = RankWeights()
    values = {}
    for name in ("hook", "cliffhanger", "standalone"):
        raw = os.getenv(f"RANK_WEIGHT_{name.upper()}", "").strip()
        try:
            values[name] = float(raw) if raw else getattr(defaults, name)
        except ValueError:
            raise ValueError(f"RANK_WEIGHT_{name.upper()} must be a number, got '{raw}'. Check your .env file.") from None
        if values[name] < 0:
            raise ValueError(f"RANK_WEIGHT_{name.upper()} cannot be negative. Check your .env file.")
    if sum(values.values()) == 0:
        raise ValueError("The RANK_WEIGHT_ values cannot all be zero. Check your .env file.")
    return RankWeights(**values)


def load_config() -> LLMConfig:
    load_dotenv(ROOT / ".env")
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    model = os.getenv("LLM_MODEL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if provider not in PROVIDERS:
        raise ValueError(f"LLM_PROVIDER must be one of {PROVIDERS}, got '{provider}'. Check your .env file.")
    if not model:
        raise ValueError("LLM_MODEL is not set. Check your .env file.")
    if not api_key:
        raise ValueError("LLM_API_KEY is not set. Check your .env file.")
    return LLMConfig(provider, model, api_key, os.getenv("LLM_BASE_URL", "").strip() or None)
