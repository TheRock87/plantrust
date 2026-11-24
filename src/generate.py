"""Generate 60 synthetic houses (truth.json) and simulated 360-degree tour measurements (tour.json).

Houses are two rows of rectangular rooms that share walls. Every number is seeded.
A tour door miscount has a cause, kept on the truth room only (`door_cause`): one door too many
is an archway (opening, no door), one too few is a hidden door. Only the notes reveal it.
"""
import random
from collections import Counter

from .common import DATA, N_HOUSES, SEED, dims, save, walls

LABELS = ["kitchen", "bedroom", "bathroom", "living", "hallway", "stairwell", "closet"]
DOOR_WIDTHS = [2.5, 3.0]


def split_width(rng, total, count, min_w=5.0):
    """Cut a row of length `total` into `count` widths of at least `min_w`, on a 0.5 ft grid."""
    while True:
        cuts = sorted(rng.choice([x / 2 for x in range(10, int(total * 2) - 9)]) for _ in range(count - 1))
        edges = [0.0] + cuts + [float(total)]
        widths = [b - a for a, b in zip(edges, edges[1:])]
        if all(w >= min_w for w in widths):
            return widths


def make_house(rng, idx):
    hid = f"h{idx:02d}"
    n = rng.randint(4, 9)
    top = (n + 1) // 2
    width = rng.choice(range(30, 52, 2))
    depths = [rng.choice(range(10, 17)), rng.choice(range(10, 17))]
    rects = []
    y = 0.0
    for depth, count in zip(depths, [top, n - top]):
        x = 0.0
        for w in split_width(rng, width, count):
            rects.append([[x, y], [x + w, y], [x + w, y + depth], [x, y + depth]])
            x += w
        y += depth

    # Labels: largest rooms are living and kitchen, then a bedroom and a bathroom, the rest drawn at random.
    order = sorted(range(n), key=lambda i: -dims(rects[i])[0] * dims(rects[i])[1])
    labels = [None] * n
    for i, lab in zip(order, ["living", "kitchen", "bedroom", "bathroom"]):
        labels[i] = lab
    has_stairs = False
    for i in order[4:]:
        w, d = dims(rects[i])
        pool = ["bedroom", "hallway", "closet", "bathroom"] + ([] if has_stairs else ["stairwell"])
        if min(w, d) < 7:
            pool = ["hallway", "closet"] + ([] if has_stairs else ["stairwell"])
        labels[i] = rng.choice(pool)
        has_stairs |= labels[i] == "stairwell"

    rooms = []
    for i, (poly, label) in enumerate(zip(rects, labels)):
        flags = []
        ceiling = 8.0
        if label == "stairwell":
            ceiling = 17.0
            flags = ["stairs", "tall_ceiling"]
        elif label == "living" and rng.random() < 0.3:
            ceiling = float(rng.choice([14, 15, 16, 18]))
            flags = ["tall_ceiling"]
        if label in ("living", "kitchen") and rng.random() < 0.15:
            flags.append("glass_wall")
        n_doors = 1 if label in ("closet", "bathroom", "stairwell") else rng.choice([1, 1, 2])
        doors = [{"wall": rng.randrange(4), "width": rng.choice(DOOR_WIDTHS)} for _ in range(n_doors)]
        rooms.append({
            "id": f"{hid}-r{i}",
            "label": label,
            "polygon": poly,
            "ceiling": ceiling,
            "doors": doors,
            "affected": rng.random() < 0.6,
            "flags": flags,
            "door_cause": None,  # set by make_tour; plant.py removes it from the AI plan
        })
    if not any(r["affected"] for r in rooms):
        rooms[0]["affected"] = True
    return {"id": hid, "rooms": rooms}


def make_tour(rng, house):
    """What a 360-degree tour would measure: noisy walls, ceiling, door count and label."""
    out = {}
    for r in house["rooms"]:
        doors = len(r["doors"])
        if rng.random() < 0.08:
            delta = rng.choice([-1, 1])
            doors = max(0, doors + delta)
            r["door_cause"] = "archway" if delta > 0 else "hidden_door"  # on the truth room, never in the tour
        label = r["label"] if rng.random() > 0.05 else rng.choice([l for l in LABELS if l != r["label"]])
        out[r["id"]] = {
            "walls": [round(w * (1 + rng.uniform(-0.02, 0.02)), 1) for w in walls(r["polygon"])],
            "ceiling": round(r["ceiling"] + rng.uniform(-0.3, 0.3), 1),
            "doors": doors,
            "label": label,
        }
    return out


def main():
    truth, tour = {}, {}
    for i in range(1, N_HOUSES + 1):
        house = make_house(random.Random(SEED * 1000 + i), i)
        truth[house["id"]] = house
        tour[house["id"]] = make_tour(random.Random(SEED * 2000 + i), house)
    save(DATA / "truth.json", truth)
    save(DATA / "tour.json", tour)
    rooms = [r for h in truth.values() for r in h["rooms"]]
    causes = Counter(r["door_cause"] for r in rooms if r["door_cause"])
    print(f"generate: {len(truth)} houses, {len(rooms)} rooms, door miscounts {sum(causes.values())} "
          f"({sum(causes.values()) / len(rooms):.1%}): {dict(sorted(causes.items()))}")


if __name__ == "__main__":
    main()
