"""Copy truth.json into ai_plan.json and plant 0 to 3 known errors per house (answers.json is the key).

About a quarter of E1 and E2 errors are subtle (walls 4 to 6 % off, ceilings 0.7 to 1.0 ft off).
"""
import copy
import random
from collections import Counter

from .common import DATA, SEED, dims, load, save

ERRORS = {
    "E1": "Wall length wrong",
    "E2": "Ceiling height wrong",
    "E3": "Missing door",
    "E4": "Missing room",
    "E5": "Rooms overlap",
    "E6": "Wet room left out",
}
SUBTLE_SHARE = 0.25


def new_length(rng, old, lo, hi):
    """A length lo..hi (as a fraction) longer or shorter than `old`, on the 0.1 ft grid."""
    while True:  # redraw if rounding pushes a short wall out of the range
        new = round(old * (1 + rng.uniform(lo, hi) * rng.choice([-1, 1])), 1)
        if lo <= abs(new / old - 1) <= hi:
            return new


def neighbours(rooms, room):
    """Rooms in the same row that share a vertical wall with `room`: (other, side) with side +1 = right."""
    (x0, y0), (x1, _), (_, y1) = room["polygon"][0], room["polygon"][1], room["polygon"][2]
    out = []
    for o in rooms:
        if o is room:
            continue
        (ox0, oy0), (ox1, _) = o["polygon"][0], o["polygon"][1]
        if oy0 == y0 and ox0 == x1:
            out.append((o, +1))
        if oy0 == y0 and ox1 == x0:
            out.append((o, -1))
    return out


def set_x(room, x0, x1):
    p = room["polygon"]
    p[0][0] = p[3][0] = round(x0, 1)
    p[1][0] = p[2][0] = round(x1, 1)


def plant_one(rng, code, rooms, used, subtle=False):
    free = [r for r in rooms if r["id"] not in used]
    if code == "E1":
        r = rng.choice(free)
        lo, hi = (0.04, 0.06) if subtle else (0.08, 0.20)
        p = r["polygon"]
        w, d = dims(p)
        if rng.random() < 0.5:  # stretch or shrink the width
            old, new = w, new_length(rng, w, lo, hi)
            set_x(r, p[0][0], p[0][0] + new)
        else:  # stretch or shrink the depth
            old, new = d, new_length(rng, d, lo, hi)
            p[2][1] = p[3][1] = round(p[0][1] + new, 1)
        return r, f"{'stretched' if new > old else 'shrunk'} by {abs(new / old - 1):.0%}"
    if code == "E2":
        if subtle:  # a small slip on any room
            r = rng.choice(free)
            new = round(r["ceiling"] + rng.uniform(0.7, 1.0) * rng.choice([-1, 1]), 1)
        else:  # tall ceilings drawn at a standard height, or a standard one drawn at 10 ft
            tall = [r for r in free if r["ceiling"] >= 12]
            r = rng.choice(tall) if tall and rng.random() < 0.7 else rng.choice(free)
            new = 8.0 if r["ceiling"] >= 12 else 10.0
        old, r["ceiling"] = r["ceiling"], new
        return r, f"ceiling {old:g} ft drawn as {new:g} ft"
    if code == "E3":
        r = rng.choice([x for x in free if x["doors"]])
        r["doors"].pop(rng.randrange(len(r["doors"])))
        return r, "one door removed"
    if code == "E4":
        r = rng.choice(free)
        rooms.remove(r)
        return r, "room deleted from the plan"
    if code == "E5":
        cands = [(r, n) for r in free for n in neighbours(rooms, r)]
        if not cands:
            return None, ""
        r, (other, side) = rng.choice(cands)
        shift = rng.choice([1.0, 1.5, 2.0])
        p = r["polygon"]
        if side > 0:
            set_x(r, p[0][0], p[1][0] + shift)
        else:
            set_x(r, p[0][0] - shift, p[1][0])
        return r, f"extended {shift:g} ft into {other['id']}"
    if code == "E6":  # only the technician's notes show that this room is wet
        wet = [r for r in free if r["affected"]]
        if not wet:
            return None, ""
        r = rng.choice(wet)
        r["affected"] = False
        return r, "wet room marked not affected"
    raise ValueError(code)


def main():
    truth = load(DATA / "truth.json")
    plans, answers = {}, {}
    for i, (hid, house) in enumerate(sorted(truth.items()), start=1):
        rng = random.Random(SEED * 3000 + i)
        plan = copy.deepcopy(house)
        for r in plan["rooms"]:
            del r["door_cause"]  # the truth's secret: the agent may learn it only from the notes
        k = rng.choices([0, 1, 2, 3], weights=[15, 30, 30, 25])[0]
        codes = rng.sample(sorted(ERRORS), k)
        used, key = set(), []
        for code in codes:
            if code == "E4" and len(plan["rooms"]) <= 3:
                continue
            subtle = code in ("E1", "E2") and rng.random() < SUBTLE_SHARE
            room, detail = plant_one(rng, code, plan["rooms"], used, subtle)
            if room is None:
                continue
            used.add(room["id"])
            key.append({"room_id": room["id"], "code": code, "detail": detail, "subtle": subtle})
        plans[hid] = plan
        answers[hid] = key
    save(DATA / "ai_plan.json", plans)
    save(DATA / "answers.json", answers)
    errs = [e for v in answers.values() for e in v]
    clean = sum(1 for v in answers.values() if not v)
    per_code = Counter(e["code"] for e in errs)
    subtle = Counter(e["code"] for e in errs if e["subtle"])
    print(f"plant: {len(errs)} errors planted, {clean} clean houses")
    for c in sorted(ERRORS):
        print(f"  {c} {ERRORS[c]:<20} {per_code[c]:>3}" + (f"  ({subtle[c]} subtle)" if c in ("E1", "E2") else ""))


if __name__ == "__main__":
    main()
