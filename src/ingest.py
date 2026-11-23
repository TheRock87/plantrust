"""Ingestion agent: map each messy past line item to a catalog code, cheapest layer first.

Layer 1, exact: the text equals a catalog description once case and punctuation are ignored.
Layer 2, fuzzy: rapidfuzz finds one clearly best catalog description, compared without its ", per unit"
          tail (a score threshold and a margin over the runner-up).
Layer 3, model: only for what is left; the model picks a code from the catalog or answers UNSURE.
Layer 4, review: anything still unsure goes on a "please review" list. Nothing is guessed into the database.
"""
import hashlib
import json
import re
import sqlite3
from typing import Literal

from pydantic import BaseModel, Field
from rapidfuzz import fuzz, process

from . import llm
from .common import DATA, TRACES, load, save
from .history import DB
from .prices import CATALOG

FUZZY_MIN = 72
FUZZY_MARGIN = 12
BATCH = 20
PROMPT_VERSION = "i1"


def norm(text):
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


CANON = {norm(d): code for code, (d, *_rest) in CATALOG.items()}
CHOICES = {code: norm(d.split(",")[0]) for code, (d, *_rest) in CATALOG.items()}


def exact(text):
    return CANON.get(norm(text))


def fuzzy(text):
    hits = process.extract(norm(text), CHOICES, scorer=fuzz.token_sort_ratio, limit=2)
    if not hits:
        return None, 0
    best, second = hits[0], hits[1] if len(hits) > 1 else (None, 0, None)
    if best[1] >= FUZZY_MIN and best[1] - second[1] >= FUZZY_MARGIN:
        return best[2], round(best[1])
    return None, round(best[1])


class Mapping(BaseModel):
    index: int
    code: str = Field(description="A catalog code, or UNSURE")


class Mappings(BaseModel):
    mappings: list[Mapping]


def model_prompt(texts):
    catalog = "\n".join(f"{c}: {d}" for c, (d, *_r) in sorted(CATALOG.items()))
    items = "\n".join(f"{i}. {t}" for i, t in enumerate(texts))
    return ("You map line items written by water-mitigation estimators to a fixed catalog.\n"
            "For each numbered line, answer the one catalog code it means. If the line could mean more than one "
            "code, or none, answer UNSURE. A wrong code is worse than UNSURE: UNSURE goes to a human.\n\n"
            f"Catalog:\n{catalog}\n\nLines:\n{items}")


def model_layer(texts):
    """Map texts with the model in batches; cached per batch on disk. Returns {text: code or None}."""
    out = {}
    if not texts:
        return out, 0
    if not llm.has_key():
        print(f"ingest: no {llm.key_names()}; {len(texts)} lines go to review without a model pass.")
        return out, 0
    calls = 0
    for start in range(0, len(texts), BATCH):
        batch = texts[start:start + BATCH]
        h = hashlib.sha256(json.dumps([llm.MODEL, PROMPT_VERSION, batch]).encode()).hexdigest()[:16]
        path = TRACES / "ingest" / f"batch_{h}.json"
        if path.exists():
            res = load(path)
        else:
            if llm.over_budget():
                print("ingest: budget cap reached; the rest goes to review.")
                break
            try:
                prompt = model_prompt(batch)
                raw, _spec = llm.invoke_with_fallback(
                    lambda m: m.with_structured_output(Mappings, include_raw=True).invoke(prompt))
                parsed = raw["parsed"].mappings if raw.get("parsed") else []
                u = llm.usage([raw["raw"]])
                res = {"texts": batch, "answers": {str(m.index): m.code for m in parsed}, "usage": u}
                llm.record(u)
                calls += 1
            except Exception as e:  # a failed batch goes to review, never into the database
                print(f"ingest: model batch failed ({type(e).__name__}: {str(e)[:100]}); batch goes to review.")
                continue
            save(path, res)
        for i, t in enumerate(batch):
            code = res["answers"].get(str(i))
            out[t] = code if code in CATALOG else None
    return out, calls


def main():
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT id, original_description FROM job_items").fetchall()
    texts = sorted({t for _, t in rows})
    layer, code_of = {}, {}
    left = []
    for t in texts:
        c = exact(t)
        if c:
            layer[t], code_of[t] = "exact", c
            continue
        c, _score = fuzzy(t)
        if c:
            layer[t], code_of[t] = "fuzzy", c
            continue
        left.append(t)
    mapped, calls = model_layer(left)
    for t in left:
        if mapped.get(t):
            layer[t], code_of[t] = "model", mapped[t]
        else:
            layer[t], code_of[t] = "review", None

    con.executemany("UPDATE job_items SET item_code = ?, mapped_by = ? WHERE id = ?",
                    [(code_of[t], layer[t], i) for i, t in rows])
    con.commit()
    con.close()

    truth = load(DATA / "history_truth.json")
    hold = load(DATA / "history_holdout.json")["ingest_lines"]
    text_of = dict(rows)
    per = {k: {"settled": 0, "correct": 0} for k in ("exact", "fuzzy", "model", "review")}
    examples = []
    for lid in hold:
        t = text_of[lid]
        k = layer[t]
        per[k]["settled"] += 1
        per[k]["correct"] += int(code_of[t] == truth[str(lid)])
        if k == "model" and len(examples) < 6:
            examples.append({"text": t, "code": code_of[t], "correct": code_of[t] == truth[str(lid)]})
    review = sorted({t for t in texts if layer[t] == "review"})
    out = {
        "holdout_lines": len(hold), "per_layer": per, "model_calls": calls,
        "all_lines": len(rows), "unique_texts": len(texts),
        "unique_by_layer": {k: sum(1 for t in texts if layer[t] == k) for k in per},
        "review_examples": review[:12], "model_examples": examples,
        "model_ran": llm.has_key(),
    }
    save(DATA / "ingest_scores.json", out)
    print("ingest (holdout of 100):", {k: f"{v['correct']}/{v['settled']}" for k, v in per.items()})


if __name__ == "__main__":
    main()
