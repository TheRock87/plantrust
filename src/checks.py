"""Plain-code checks: exact, free, and run on every room before any model is called.

v1: each room gets `pass`, `fail` (send to drafter, with the reason) or `unclear` (the agent decides).
v2: each room also gets a `route`, one item per problem, saying who handles it:
- `code`: wall more than 5 % off or ceiling more than 1 ft off; fixes.py writes the edit from the tour;
- `drafter`: wall or ceiling near the limit, room missing from the plan, room the tour never captured;
- `notes`: door counts differ, or the plan says not wet and the room has a note; words decide (baseline or agent).
Weak spots, label differences and overlaps add nothing when the measurements match the tour.
Routing uses the data fields only, never words in the note.
"""
from collections import Counter

from shapely.geometry import Polygon

from .common import DATA, load, save, walls
from .cost import room_cost, tour_cost

WALL_TOL = 0.05      # fail above 5 % difference from the tour
WALL_NEAR = 0.035    # unclear between 3.5 % and 5 %
CEIL_TOL = 1.0       # fail above 1 ft
CEIL_NEAR = 0.6      # unclear between 0.6 and 1 ft
OVERLAP_MIN = 1.0    # sq ft
RISK_FLAGS = {"stairs": "stairwell", "glass_wall": "glass wall", "tall_ceiling": "tall ceiling"}


def overlaps(rooms):
    polys = {r["id"]: Polygon(r["polygon"]) for r in rooms}
    out = {rid: [] for rid in polys}
    ids = sorted(polys)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            area = polys[a].intersection(polys[b]).area
            if area > OVERLAP_MIN:
                out[a].append({"other": b, "sqft": round(area, 1)})
                out[b].append({"other": a, "sqft": round(area, 1)})
    return out


def check_room(room, tour_room, room_overlaps, note):
    fails, unclear, route = [], [], []
    plan_walls = walls(room["polygon"])
    diffs = [(p - t) / t for p, t in zip(plan_walls, tour_room["walls"])]
    worst = max(range(4), key=lambda i: abs(diffs[i]))
    wall_txt = (f"wall {worst + 1} is {plan_walls[worst]:.1f} ft in the plan, "
                f"{tour_room['walls'][worst]:.1f} ft in the tour ({diffs[worst]:+.1%})")
    if abs(diffs[worst]) > WALL_TOL:
        fails.append("Wall length: " + wall_txt)
        route.append({"kind": "wall", "to": "code", "why": wall_txt})
    elif abs(diffs[worst]) > WALL_NEAR:
        unclear.append("Wall length near the limit: " + wall_txt)
        route.append({"kind": "wall_near", "to": "drafter", "why": wall_txt})

    dc = room["ceiling"] - tour_room["ceiling"]
    ceil_txt = f"ceiling {room['ceiling']:g} ft in the plan, {tour_room['ceiling']:g} ft in the tour"
    if abs(dc) > CEIL_TOL:
        fails.append("Ceiling: " + ceil_txt)
        route.append({"kind": "ceiling", "to": "code", "why": ceil_txt})
    elif abs(dc) > CEIL_NEAR:
        unclear.append("Ceiling near the limit: " + ceil_txt)
        route.append({"kind": "ceiling_near", "to": "drafter", "why": ceil_txt})

    if len(room["doors"]) != tour_room["doors"]:
        unclear.append(f"Doors: {len(room['doors'])} in the plan, {tour_room['doors']} in the tour "
                       "(tour door counts are sometimes off by one)")
        route.append({"kind": "doors", "to": "notes",
                      "why": f"{len(room['doors'])} doors in the plan, {tour_room['doors']} in the tour"})
    if not room["affected"] and note:
        route.append({"kind": "wet", "to": "notes", "why": "plan says not wet; the technician's note may say otherwise"})
    if room["label"] != tour_room["label"]:
        unclear.append(f"Label: '{room['label']}' in the plan, '{tour_room['label']}' in the tour")
    for o in room_overlaps:
        unclear.append(f"Overlaps {o['other']} by {o['sqft']:g} sq ft")
    risky = [RISK_FLAGS[f] for f in room["flags"] if f in RISK_FLAGS]
    if risky:
        unclear.append("Known weak spot for scanners: " + ", ".join(risky))

    status = "fail" if fails else "unclear" if unclear else "pass"
    plan_usd = room_cost(room)["usd"]
    tour_usd = tour_cost(tour_room, room["affected"])["usd"]
    return {
        "status": status,
        "route": route,
        "reasons": fails + unclear if status != "pass" else ["All checks pass"],
        "numbers": {
            "plan_walls": plan_walls, "tour_walls": tour_room["walls"],
            "worst_wall_diff_pct": round(100 * diffs[worst], 1),
            "plan_ceiling": room["ceiling"], "tour_ceiling": tour_room["ceiling"],
            "plan_doors": len(room["doors"]), "tour_doors": tour_room["doors"],
            "plan_label": room["label"], "tour_label": tour_room["label"],
            "overlaps": room_overlaps, "flags": room["flags"], "affected": room["affected"],
        },
        "est_cost_at_risk_usd": round(abs(plan_usd - tour_usd), 2),
    }


def check_house(plan, tour, notes):
    """`notes` maps room id to the technician's note (a room may have none)."""
    ov = overlaps(plan["rooms"])
    out = {}
    for room in plan["rooms"]:
        if room["id"] not in tour:
            # Scanners can draw rooms that are not there (reflections); nothing to compare, so a human looks.
            why = f"The plan has a {room['label']} that the tour never captured"
            out[room["id"]] = {
                "status": "fail", "not_in_tour": True,
                "route": [{"kind": "not_in_tour", "to": "drafter", "why": why}],
                "reasons": [why],
                "numbers": {"plan_walls": walls(room["polygon"]), "plan_ceiling": room["ceiling"],
                            "plan_doors": len(room["doors"]), "plan_label": room["label"]},
                "est_cost_at_risk_usd": room_cost(room)["usd"],
            }
            continue
        out[room["id"]] = check_room(room, tour[room["id"]], ov[room["id"]], notes.get(room["id"]))
    plan_ids = {r["id"] for r in plan["rooms"]}
    for rid, t in tour.items():
        if rid not in plan_ids:
            w = (t["walls"][0] + t["walls"][2]) / 2
            d = (t["walls"][1] + t["walls"][3]) / 2
            why = f"Tour captured a {t['label']} ({w:.1f} x {d:.1f} ft) that is missing from the plan"
            out[rid] = {
                "status": "fail", "missing": True,
                "route": [{"kind": "missing", "to": "drafter", "why": why}],
                "reasons": [why],
                "numbers": {"tour_walls": t["walls"], "tour_ceiling": t["ceiling"], "tour_label": t["label"]},
                # The plan has no room here, so everything the tour measured is at risk (assumes affected).
                "est_cost_at_risk_usd": tour_cost(t, True)["usd"],
            }
    return out


def notes_questions(checks):
    """(room_id, route item) for every door and wet question: only the words in the note can answer them."""
    return [(rid, i) for h in checks.values() for rid, c in h.items() for i in c["route"] if i["to"] == "notes"]


def main():
    plans, tours, notes =load(DATA / "ai_plan.json"), load(DATA / "tour.json"), load(DATA / "notes.json")
    results = {hid: check_house(plans[hid], tours[hid], notes) for hid in sorted(plans)}
    save(DATA / "checks.json", results)
    counts = {}
    for house in results.values():
        for r in house.values():
            counts[r["status"]] = counts.get(r["status"], 0) + 1
    routes = Counter(f"{i['kind']}->{i['to']}" for h in results.values() for r in h.values() for i in r["route"])
    print("checks: v1 status", counts)
    print("checks: v2 route", dict(sorted(routes.items())))


if __name__ == "__main__":
    main()
