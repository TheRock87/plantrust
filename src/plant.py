"""Copy truth.json into ai_plan.json and plant 0 to 2 known errors per house (answers.json is the key)."""
import copy
import random

from .common import DATA, SEED, dims, load, save

ERRORS = {
    "E1": "Wall length wrong",
    "E2": "Ceiling height wrong",
    "E3": "Missing door",
    "E4": "Missing room",
    "E5": "Rooms overlap",
}


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


def plant_one(rng, code, rooms, used):
    free = [r for r in rooms if r["id"] not in used]
    if code == "E1":
        r = rng.choice(free)
        f = rng.uniform(0.08, 0.20) * rng.choice([-1, 1])
        p = r["polygon"]
        if rng.random() < 0.5:  # stretch or shrink the width
            w, _ = dims(p)
            set_x(r, p[0][0], p[0][0] + w * (1 + f))
        else:  # stretch or shrink the depth
            _, d = dims(p)
            p[2][1] = p[3][1] = round(p[0][1] + d * (1 + f), 1)
        return r, f"{'stretched' if f > 0 else 'shrunk'} by {abs(f):.0%}"
    if code == "E2":
        tall = [r for r in free if r["ceiling"] >= 12]
        r = rng.choice(tall) if tall and rng.random() < 0.7 else rng.choice(free)
        old = r["ceiling"]
        r["ceiling"] = 8.0 if old >= 12 else 10.0
        return r, f"ceiling {old:g} ft drawn as {r['ceiling']:g} ft"
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
    raise ValueError(code)


def main():
    truth = load(DATA / "truth.json")
    plans, answers = {}, {}
    for i, (hid, house) in enumerate(sorted(truth.items()), start=1):
        rng = random.Random(SEED * 3000 + i)
        plan = copy.deepcopy(house)
        k = rng.choices([0, 1, 2], weights=[25, 45, 30])[0]
        codes = rng.sample(sorted(ERRORS), k)
        used, key = set(), []
        for code in codes:
            if code == "E4" and len(plan["rooms"]) <= 3:
                continue
            room, detail = plant_one(rng, code, plan["rooms"], used)
            if room is None:
                continue
            used.add(room["id"])
            key.append({"room_id": room["id"], "code": code, "detail": detail})
        plans[hid] = plan
        answers[hid] = key
    save(DATA / "ai_plan.json", plans)
    save(DATA / "answers.json", answers)
    n = sum(len(v) for v in answers.values())
    clean = sum(1 for v in answers.values() if not v)
    print(f"plant: {n} errors planted, {clean} clean houses")


if __name__ == "__main__":
    main()
