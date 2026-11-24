"""Code proposals: where a rule gives the answer, code writes the edit; other checks become drafter items.

A proposal is {room_id, action, args, by, quote_or_evidence, est_cost_at_risk_usd} (plus `kind`, the route item
it answers). Nothing is applied to the plan here: the drafter approves or rejects each edit (drafter.py).
Reads only the AI plan, the tour and checks.json, never the truth.
"""
import copy

from shapely.geometry import Polygon

from .checks import OVERLAP_MIN, WALL_TOL
from .common import DATA, dims, load, save
from .cost import TOUR_DOOR_WIDTH_FT, room_cost

EDITS = ("set_room_size", "set_ceiling", "add_door", "mark_wet")


def apply(room, p):
    """A copy of the plan room with one edit applied (a draft; the final plan never changes here)."""
    r, a = copy.deepcopy(room), p["args"]
    if p["action"] == "set_room_size":
        (x0, y0), (x1, _) = r["polygon"][0], r["polygon"][1]
        if a["keep"] == "right":
            x0 = round(x1 - a["width"], 1)
        else:
            x1 = round(x0 + a["width"], 1)
        y1 = round(y0 + a["depth"], 1)  # planted depth errors move the top wall only
        r["polygon"] = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    elif p["action"] == "set_ceiling":
        r["ceiling"] = a["ceiling"]
    elif p["action"] == "add_door":
        r["doors"].append({"wall": a["wall"], "width": TOUR_DOOR_WIDTH_FT})
    elif p["action"] == "mark_wet":
        r["affected"] = True
    else:
        raise ValueError(p["action"])
    return r


def tour_size(t):
    """Width and depth from the tour: average of opposite walls."""
    return round((t["walls"][0] + t["walls"][2]) / 2, 1), round((t["walls"][1] + t["walls"][3]) / 2, 1)


def size_fix(room, tour_room, rooms):
    """Set only the dimension that is more than 5 % off. Keep the wall that does not overlap a room in the same row.

    `rooms` are the trusted neighbours only (walls match the tour): a neighbour that is itself wrong must not
    decide which wall of this room stays.
    """
    (w, d), (tw, td), t = dims(room["polygon"]), tour_size(tour_room), tour_room["walls"]
    off = lambda plan_len, a, b: max(abs(plan_len / a - 1), abs(plan_len / b - 1)) > WALL_TOL  # same rule as checks
    me = Polygon(room["polygon"])
    x0, y0 = room["polygon"][0]
    left = any(o["polygon"][0][1] == y0 and o["polygon"][0][0] < x0
               and me.intersection(Polygon(o["polygon"])).area > OVERLAP_MIN for o in rooms if o is not room)
    return {"width": tw if off(w, t[0], t[2]) else w,
            "depth": td if off(d, t[1], t[3]) else d,
            "keep": "right" if left else "left"}


def proposal(room_id, kind, action, args, evidence, usd):
    return {"room_id": room_id, "kind": kind, "action": action, "args": args, "by": "code",
            "quote_or_evidence": evidence, "est_cost_at_risk_usd": round(usd, 2)}


def propose_house(plan, tour, checks):
    rooms = {r["id"]: r for r in plan["rooms"]}
    trusted = [r for r in plan["rooms"] if not any(i["kind"] == "wall" for i in checks[r["id"]]["route"])]
    out = []
    for rid, chk in sorted(checks.items()):
        for item in chk["route"]:
            if item["to"] == "notes":
                continue  # words decide: baseline or agent, or a drafter when no one reads the notes
            if item["to"] == "drafter":
                if item["kind"] == "missing":
                    w, d = tour_size(tour[rid])
                    q = f"draw the missing {w:.1f} x {d:.1f} ft {tour[rid]['label']}"
                else:
                    q = f"check: {item['why']}"
                out.append(proposal(rid, item["kind"], "ask_drafter", {"question": q}, item["why"],
                                    chk["est_cost_at_risk_usd"]))
                continue
            room = rooms[rid]
            if item["kind"] == "wall":
                p = proposal(rid, "wall", "set_room_size", size_fix(room, tour[rid], trusted), item["why"], 0)
            else:
                p = proposal(rid, "ceiling", "set_ceiling", {"ceiling": tour[rid]["ceiling"]}, item["why"], 0)
            p["est_cost_at_risk_usd"] = round(abs(room_cost(apply(room, p))["usd"] - room_cost(room)["usd"]), 2)
            out.append(p)
    return out


def main():
    plans, tours, checks = load(DATA / "ai_plan.json"), load(DATA / "tour.json"), load(DATA / "checks.json")
    code = [p for hid in sorted(plans) for p in propose_house(plans[hid], tours[hid], checks[hid])]
    save(DATA / "proposals.json", {"code": code})
    edits = sum(p["action"] in EDITS for p in code)
    print(f"fixes: {edits} code edits, {len(code) - edits} drafter items")


if __name__ == "__main__":
    main()
