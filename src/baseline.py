"""Keyword baseline: the cheap rule the agent must beat (row C). Written once and left alone.

For each notes question (checks.notes_questions):
- wet question: the note has "wet", "water" or "soaked" -> mark_wet, else no_change;
- door question: the note has "archway" or "opening" -> no_change, else ask_drafter
  (no keyword can tell a missing door from a tour miscount, so a drafter decides).
Plain substring match on the lower-case sentence, as a quick script would do.
"""
import re

from .checks import notes_questions
from .common import DATA, load, save
from .fixes import question_usd

WET_WORDS = ("wet", "water", "soaked")
ARCH_WORDS = ("archway", "opening")


def answer(kind, note):
    """(action, quote) for one question; the quote is the first sentence with a keyword."""
    words = {"wet": WET_WORDS, "doors": ARCH_WORDS}[kind]
    quote = next((s for s in re.split(r"(?<=\.)\s+", note) if any(w in s.lower() for w in words)), "")
    if kind == "wet":
        return ("mark_wet", quote) if quote else ("no_change", "")
    return ("no_change", quote) if quote else ("ask_drafter", "")


def propose(checks, plans, notes):
    out = []
    for rid, item in notes_questions(checks):
        action, quote = answer(item["kind"], notes[rid])
        room = plans[rid]
        p = {"room_id": rid, "kind": item["kind"], "action": action, "args": {}, "by": "baseline",
             "quote_or_evidence": quote or item["why"], "est_cost_at_risk_usd": 0.0}
        if action in ("mark_wet", "ask_drafter"):
            p["est_cost_at_risk_usd"] = question_usd(item["kind"], room)
        if action == "ask_drafter":
            p["args"] = {"question": f"check: {item['why']}"}
        out.append(p)
    return out


def main():
    checks, notes = load(DATA / "checks.json"), load(DATA / "notes.json")
    plans = {r["id"]: r for h in load(DATA / "ai_plan.json").values() for r in h["rooms"]}
    proposals = load(DATA / "proposals.json")
    proposals["baseline"] = propose(checks, plans, notes)
    save(DATA / "proposals.json", proposals)
    n = {}
    for p in proposals["baseline"]:
        n[f"{p['kind']}->{p['action']}"] = n.get(f"{p['kind']}->{p['action']}", 0) + 1
    print("baseline:", dict(sorted(n.items())))


if __name__ == "__main__":
    main()
