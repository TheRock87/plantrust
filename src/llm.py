"""One place that builds the chat model, reads the key, and counts tokens and cost.

Default provider: Groq's free tier (no card). Override with PLANTRUST_MODEL, for example
PLANTRUST_MODEL=groq:llama-3.3-70b-versatile. The key comes from the environment or a local .env file.
"""
import os

from .common import ROOT, TRACES, load, save

MODEL = os.environ.get("PLANTRUST_MODEL", "groq:openai/gpt-oss-120b")
KEY_ENV = {"groq": "GROQ_API_KEY"}
# USD per million tokens. The free tier bills nothing; the cap still protects a paid key.
PRICE_PER_M = {"free_tier": {"input": 0.0, "output": 0.0}}
BUDGET_USD = 4.50
REQUESTS_PER_MINUTE = 24  # under the free tier's per-minute limit

_model = None


def provider():
    return MODEL.split(":", 1)[0]


def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def has_key():
    _load_env()
    return bool(os.environ.get(KEY_ENV.get(provider(), ""), ""))


def get_model():
    """The shared chat model, rate-limited. Call has_key() first."""
    global _model
    if _model is None:
        from langchain.chat_models import init_chat_model
        from langchain_core.rate_limiters import InMemoryRateLimiter

        limiter = InMemoryRateLimiter(requests_per_second=REQUESTS_PER_MINUTE / 60, max_bucket_size=1)
        _model = init_chat_model(MODEL, temperature=0, max_retries=6, rate_limiter=limiter)
    return _model


def usage(messages):
    tin = sum((getattr(m, "usage_metadata", None) or {}).get("input_tokens", 0) for m in messages)
    tout = sum((getattr(m, "usage_metadata", None) or {}).get("output_tokens", 0) for m in messages)
    p = PRICE_PER_M["free_tier"]
    return {"input_tokens": tin, "output_tokens": tout,
            "usd": round(tin / 1e6 * p["input"] + tout / 1e6 * p["output"], 6)}


LEDGER = TRACES / "_spend.json"


def ledger():
    return load(LEDGER) if LEDGER.exists() else {"usd": 0.0, "calls": 0, "input_tokens": 0, "output_tokens": 0}


def record(u):
    led = ledger()
    for k in ("input_tokens", "output_tokens"):
        led[k] = led.get(k, 0) + u[k]
    led["usd"] = round(led["usd"] + u["usd"], 6)
    led["calls"] += 1
    save(LEDGER, led)
    return led


def over_budget():
    return ledger()["usd"] >= BUDGET_USD
