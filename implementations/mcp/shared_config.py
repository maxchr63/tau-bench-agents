"""
Shared LiteLLM configuration for all tau-bench agents.

Keep this module small + deterministic: import it before anything that calls LiteLLM.
"""

from __future__ import annotations

import os

import litellm

# -----------------------------------------------------------------------------
# Provider selection (accept a couple aliases to reduce "it doesn't work" cases)
# -----------------------------------------------------------------------------
# Preferred: USE_PROVIDER=openrouter|openai
# Back-compat: LLM_PROVIDER=openrouter|openai (used by older shell scripts)
USE_PROVIDER = (os.environ.get("USE_PROVIDER") or os.environ.get("LLM_PROVIDER") or "openrouter").strip().lower()

# -----------------------------------------------------------------------------
# Global LiteLLM safety defaults (avoid hangs / retry storms)
# -----------------------------------------------------------------------------
litellm.request_timeout = float(os.environ.get("LITELLM_REQUEST_TIMEOUT", "60"))
litellm.num_retries = int(os.environ.get("LITELLM_NUM_RETRIES", "1"))

# GPT-5 and other providers can reject unsupported params; drop them automatically.
litellm.drop_params = True


def _openrouter_model(model: str) -> str:
    """Normalize model naming for OpenRouter.

    If user provides e.g. `openai/gpt-4o-mini`, convert to `openrouter/openai/gpt-4o-mini`.
    """

    model = (model or "").strip()
    if not model:
        return model
    return model if model.startswith("openrouter/") else f"openrouter/{model}"


if USE_PROVIDER == "openrouter":
    # Model can be set via TAU_USER_MODEL or OPENROUTER_MODEL for convenience.
    _model = (
        os.environ.get("TAU_USER_MODEL")
        or os.environ.get("OPENROUTER_MODEL")
        or "anthropic/claude-haiku-4.5"
    )
    TAU_USER_MODEL = _openrouter_model(_model)
    TAU_USER_PROVIDER = os.environ.get("TAU_USER_PROVIDER", "openrouter")

    litellm.api_base = os.environ.get("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
    litellm.set_verbose = False

    # OpenRouter key (tau-bench sometimes looks for OPENAI_API_KEY even when routing elsewhere).
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if openrouter_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = openrouter_key
    if not openrouter_key:
        print("[config] OPENROUTER_API_KEY is not set; OpenRouter calls will fail.")

elif USE_PROVIDER == "openai":
    TAU_USER_MODEL = (
        os.environ.get("TAU_USER_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or "gpt-4o-mini"
    )
    TAU_USER_PROVIDER = os.environ.get("TAU_USER_PROVIDER", "openai")

    litellm.set_verbose = False
    if not os.environ.get("OPENAI_API_KEY"):
        print("[config] OPENAI_API_KEY is not set; OpenAI calls will fail.")

else:
    raise ValueError(
        f"Invalid provider {USE_PROVIDER!r}. Set USE_PROVIDER=openrouter|openai (or legacy LLM_PROVIDER)."
    )


__all__ = ["USE_PROVIDER", "TAU_USER_MODEL", "TAU_USER_PROVIDER"]
