"""One place that builds the chat models, reads the keys, and counts tokens and cost.

Main model: Mistral `mistral-small-latest` on Mistral's free mode (no card; the largest free allowance found
in November 2026). Fallback: Gemini Flash-Lite on Google's free tier. Free tiers change without notice, so
when the main model fails (rate limit, outage), LangChain's ModelFallbackMiddleware retries on the fallback.
Override with PLANTRUST_MODEL / PLANTRUST_FALLBACK, for example PLANTRUST_FALLBACK=none.
Keys come from the environment or a local .env file: MISTRAL_API_KEY, GOOGLE_API_KEY.
"""
import os

from .common import ROOT, TRACES, load, save

PRIMARY = os.environ.get("PLANTRUST_MODEL", "mistralai:mistral-small-latest")
FALLBACK = os.environ.get("PLANTRUST_FALLBACK", "google_genai:gemini-flash-lite-latest")
KEY_ENV = {"mistralai": "MISTRAL_API_KEY", "google_genai": "GOOGLE_API_KEY"}
REQUESTS_PER_MINUTE = {"mistralai": 50, "google_genai": 12}  # under each free tier's per-minute limit
PRICE_PER_M = {"input": 0.0, "output": 0.0}  # free tiers bill nothing; the cap still protects a paid key
BUDGET_USD = 4.50

_built = {}


def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def _provider(spec):
    return spec.split(":", 1)[0]


def specs():
    """Configured models whose key is present, main model first."""
    _load_env()
    out = []
    for spec in (PRIMARY, FALLBACK):
        if spec and spec != "none" and os.environ.get(KEY_ENV.get(_provider(spec), ""), ""):
            out.append(spec)
    return out


def has_key():
    return bool(specs())


def key_names():
    return " or ".join(KEY_ENV[_provider(s)] for s in (PRIMARY, FALLBACK) if s and s != "none")


def label():
    """What the page says about the models: the configured main model and fallback."""
    return PRIMARY + (f" (fallback {FALLBACK})" if FALLBACK and FALLBACK != "none" else "")


MODEL = label()


def _build(spec):
    if spec not in _built:
        from langchain.chat_models import init_chat_model
        from langchain_core.rate_limiters import InMemoryRateLimiter

        rpm = REQUESTS_PER_MINUTE.get(_provider(spec), 20)
        limiter = InMemoryRateLimiter(requests_per_second=rpm / 60, max_bucket_size=1)
        _built[spec] = init_chat_model(spec, temperature=0, max_retries=4, rate_limiter=limiter)
    return _built[spec]


def get_model():
    """The first available model. Call has_key() first."""
    return _build(specs()[0])


def get_fallbacks():
    return [_build(s) for s in specs()[1:]]


def agent_middleware(fallbacks):
    if not fallbacks:
        return ()
    from langchain.agents.middleware import ModelFallbackMiddleware
    return (ModelFallbackMiddleware(*fallbacks),)


def invoke_with_fallback(make_call):
    """For plain (non-agent) calls: try each available model in order; raise the last error."""
    err = None
    for spec in specs():
        try:
            return make_call(_build(spec)), spec
        except Exception as e:  # try the next model
            err = e
    raise err or RuntimeError("no model available")


def models_used(messages):
    names = []
    for m in messages:
        n = (getattr(m, "response_metadata", None) or {}).get("model_name") or \
            (getattr(m, "response_metadata", None) or {}).get("model")
        if n and n not in names:
            names.append(n)
    return names


def usage(messages):
    tin = sum((getattr(m, "usage_metadata", None) or {}).get("input_tokens", 0) for m in messages)
    tout = sum((getattr(m, "usage_metadata", None) or {}).get("output_tokens", 0) for m in messages)
    return {"input_tokens": tin, "output_tokens": tout,
            "usd": round(tin / 1e6 * PRICE_PER_M["input"] + tout / 1e6 * PRICE_PER_M["output"], 6),
            "models": models_used(messages)}


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
