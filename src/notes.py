"""Technician notes: 1 to 3 short sentences per room, like a voice note (data/notes.json).

Seeded sentences from small phrase banks. The facts come from truth.json (the technician stands in the
real house), never from the AI plan, so a note cannot copy a planted error:
- wet or dry: a wet room is mentioned 85 % of the time, a dry room 35 %, often as a negation ("no water in the closet");
- doors (70 %): the cause of a tour miscount (archway, hidden door), otherwise the real door count;
- a dry room next to a wet one may talk about that neighbour ("bath is fine, hall next to it is soaked");
- some chatter.
"""
import random
from collections import Counter

from .common import DATA, SEED, load, save
from .plant import neighbours

WET = [
    "water ran under the {room} carpet, the pad is soaked.",
    "{room} floor is wet along the walls.",
    "moisture meter reads high on the {room} drywall.",
    "standing water in the {room} when we got here.",
    "{room} is wet, baseboards are swelling.",
]
DRY = [
    "no water in the {room}.",
    "{room} is dry, meter reads normal.",
    "checked the {room}, nothing wet.",
    "{room} floor is dry, no damage.",
    "no moisture in the {room} walls.",
]
ARCHWAY = [
    "one opening is an archway, no door.",
    "the extra opening in the {room} is just an archway.",
    "open archway on one side of the {room}, there is no door in it.",
    "{room} has a cased opening, not a door.",
    "archway to the next room, no door.",
]
HIDDEN = [
    "there is a pocket door hidden in the {room} wall.",
    "one door is behind the shelving, easy to miss.",
    "found a door behind a curtain, the camera missed it.",
    "{room} has a hidden door to the next room.",
    "pocket door in the {room}, it slides into the wall.",
]
COUNT = [
    "{room} has {word} door{s}.",
    "{word} door{s} in the {room}.",
    "counted {n} door{s} in the {room}.",
    "{room}: {n} door{s} in total.",
    "the {room} has {word} door{s}, I checked.",
]
NEIGHBOUR = [
    "{room} is fine, the {other} next to it is soaked.",
    "the {other} next door is wet, not this one.",
    "water stayed in the {other} next door.",
    "the {other} beside the {room} has wet carpet.",
    "the wall to the {other} is wet on that side.",
]
CHATTER = [
    "owner moved the furniture out already.",
    "took photos of every wall.",
    "power is on, fans can go in tomorrow.",
    "lights work in here.",
    "owner asked about the timeline.",
]
SPOKEN = {"living": "living room", "hallway": "hall"}
WORD = {1: "one", 2: "two", 3: "three"}


def say(template, room, other=None):
    name = SPOKEN.get(room["label"], room["label"])
    other_name = None
    if other:
        other_name = ("other " if other["label"] == room["label"] else "") + SPOKEN.get(other["label"], other["label"])
    n = len(room["doors"])
    s = template.format(room=name, other=other_name, n=n, word=WORD.get(n, n), s="" if n == 1 else "s")
    return s[0].upper() + s[1:]


def make_note(rng, room, rooms):
    """One room's note and the kinds of fact it states (the kinds are for tests and the printout only)."""
    picks = []  # (kind, sentence), facts first so the 3-sentence cap drops chatter, not facts
    if room["affected"] and rng.random() < 0.85:
        picks.append(("wet", say(rng.choice(WET), room)))
    if not room["affected"] and rng.random() < 0.35:
        picks.append(("dry", say(rng.choice(DRY), room)))
    if rng.random() < 0.70:
        cause = room["door_cause"]
        bank = {"archway": ARCHWAY, "hidden_door": HIDDEN}.get(cause, COUNT)
        picks.append((cause or "count", say(rng.choice(bank), room)))
    wet_next = [o for o, _ in neighbours(rooms, room) if o["affected"]]
    if not room["affected"] and wet_next and rng.random() < 0.4:
        picks.append(("neighbour", say(rng.choice(NEIGHBOUR), room, rng.choice(wet_next))))
    if not picks or rng.random() < 0.3:
        picks.append(("chatter", say(rng.choice(CHATTER), room)))
    picks = picks[:3]
    rng.shuffle(picks)
    return " ".join(s for _, s in picks), [k for k, _ in picks]


def build(truth):
    notes, kinds = {}, {}
    for i, (_, house) in enumerate(sorted(truth.items()), start=1):
        rng = random.Random(SEED * 4000 + i)
        for room in house["rooms"]:
            notes[room["id"]], kinds[room["id"]] = make_note(rng, room, house["rooms"])
    return notes, kinds


def main():
    truth = load(DATA / "truth.json")
    notes, kinds = build(truth)
    save(DATA / "notes.json", notes)
    rooms = {r["id"]: r for h in truth.values() for r in h["rooms"]}
    wet = [rid for rid, r in rooms.items() if r["affected"]]
    told = sum("wet" in kinds[rid] for rid in wet)
    print(f"notes: {len(notes)} rooms; wet rooms with a wet sentence {told} of {len(wet)} ({told / len(wet):.0%}); "
          f"sentence kinds {dict(sorted(Counter(k for ks in kinds.values() for k in ks).items()))}")
    for kind in ("wet", "dry", "archway", "hidden_door", "neighbour"):  # one sample of each kind
        rid = next(rid for rid in sorted(notes) if kind in kinds[rid])
        r = rooms[rid]
        print(f"  {rid} ({r['label']}, {'wet' if r['affected'] else 'dry'}, {len(r['doors'])} door(s)"
              f"{', ' + r['door_cause'] if r['door_cause'] else ''}): {notes[rid]}")


if __name__ == "__main__":
    main()
