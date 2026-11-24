"""Simulated drafter: approves an edit only if it makes the changed part of the room match the truth.

The drafter knows the real house (truth.json). Each edit is checked on the field it changes:
walls within 2 %, ceiling within 0.5 ft, door count, wet status. ask_drafter items are manual work, not decided here.
Every edit also records `field_was_right`: the plan already had that field right, so the edit was harmful.
"""
from collections import Counter

from .common import DATA, dims, load, save
from .fixes import EDITS, apply

WALL_OK = 0.02
CEIL_OK = 0.5


def field_matches(action, room, truth_room):
    if action == "set_room_size":
        return all(abs(a / b - 1) <= WALL_OK for a, b in zip(dims(room["polygon"]), dims(truth_room["polygon"])))
    if action == "set_ceiling":
        return abs(room["ceiling"] - truth_room["ceiling"]) <= CEIL_OK
    if action == "add_door":
        return len(room["doors"]) == len(truth_room["doors"])
    if action == "mark_wet":
        return room["affected"] == truth_room["affected"]
    raise ValueError(action)


def simulated_drafter(proposal, plan_room, truth_room):
    """`approve` or `reject` one edit. Takes the plan room too: the edit is applied to it, then compared."""
    after = apply(plan_room, proposal)
    return "approve" if field_matches(proposal["action"], after, truth_room) else "reject"


def main():
    truth = {r["id"]: r for h in load(DATA / "truth.json").values() for r in h["rooms"]}
    plans = {r["id"]: r for h in load(DATA / "ai_plan.json").values() for r in h["rooms"]}
    proposals = load(DATA / "proposals.json")
    for by, items in proposals.items():
        for p in items:
            if p["action"] in EDITS:
                p["decision"] = simulated_drafter(p, plans[p["room_id"]], truth[p["room_id"]])
                p["field_was_right"] = field_matches(p["action"], plans[p["room_id"]], truth[p["room_id"]])
        n = Counter(p.get("decision", p["action"]) for p in items)
        print(f"drafter: {by}: {n['approve']} approved, {n['reject']} rejected, {n['ask_drafter']} manual items, "
              f"{n['no_change']} no change")
    save(DATA / "proposals.json", proposals)


if __name__ == "__main__":
    main()
