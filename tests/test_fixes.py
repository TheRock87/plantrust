"""v2 step 3: routing in checks.py, code proposals (fixes.py), the simulated drafter (drafter.py)."""
from collections import defaultdict

from shapely.geometry import Polygon

from src.checks import OVERLAP_MIN
from src.common import DATA, dims, load
from src.drafter import simulated_drafter
from src.fixes import apply, propose_house
from tests.test_checks import room, run, tour_of


def kinds(out, rid):
    return [(i["kind"], i["to"]) for i in out[rid]["route"]]


def test_routes():
    a = room("a", 0, 10)
    assert kinds(run([a], {"a": tour_of(a)}), "a") == []
    wide = room("a", 0, 11)
    assert kinds(run([wide], {"a": tour_of(a)}), "a") == [("wall", "code")]           # 10 % off
    near = room("a", 0, 10.4)
    assert kinds(run([near], {"a": tour_of(a)}), "a") == [("wall_near", "drafter")]  # 4 % off
    assert kinds(run([a], {"a": tour_of(a, ceiling=17)}), "a") == [("ceiling", "code")]
    assert kinds(run([a], {"a": tour_of(a, doors=2)}), "a") == [("doors", "notes")]


def test_wet_question_only_for_a_dry_plan_room_with_a_note():
    a = room("a", 0, 10)
    a["affected"] = False
    assert kinds(run([a], {"a": tour_of(a)}, {"a": "Took photos."}), "a") == [("wet", "notes")]
    assert kinds(run([a], {"a": tour_of(a)}), "a") == []


def test_weak_spot_label_and_overlap_pass_when_measurements_match():
    s = room("s", 0, 10, ceiling=17, label="stairwell", flags=["stairs", "tall_ceiling"])
    assert kinds(run([s], {"s": tour_of(s, label="hallway")}), "s") == []
    a, b = room("a", 0, 11.5), room("b", 10, 20)
    out = run([a, b], {"a": tour_of(room("a", 0, 10)), "b": tour_of(b)})
    assert kinds(out, "b") == [] and kinds(out, "a") == [("wall", "code")]


def test_missing_room_asks_the_drafter_to_draw_it():
    a, b = room("a", 0, 10), room("b", 10, 20, label="kitchen")
    tour = {"a": tour_of(a), "b": tour_of(b)}
    out = run([a], tour)
    (p,) = propose_house({"rooms": [a]}, tour, out)
    assert p["action"] == "ask_drafter" and p["args"]["question"] == "draw the missing 10.0 x 10.0 ft kitchen"


def test_overlap_fix_keeps_the_wall_that_does_not_overlap():
    left, r = room("left", 0, 10), room("r", 10, 20)
    planned = room("r", 8, 20)  # extended 2 ft to the left, into `left`
    tour = {"left": tour_of(left), "r": tour_of(r)}
    (p,) = propose_house({"rooms": [left, planned]}, tour, run([left, planned], tour))
    assert p["action"] == "set_room_size" and p["args"]["keep"] == "right"
    assert apply(planned, p)["polygon"] == r["polygon"]
    assert simulated_drafter(p, planned, r) == "approve"


def test_drafter_checks_the_changed_field_against_the_truth():
    plan, truth = room("a", 0, 10), room("a", 0, 10, doors=2)
    plan["affected"] = False
    add = {"room_id": "a", "action": "add_door", "args": {"wall": 1}}
    wet = {"room_id": "a", "action": "mark_wet", "args": {}}
    assert simulated_drafter(add, plan, truth) == "approve"
    assert simulated_drafter(wet, plan, truth) == "approve"
    truth["affected"] = False
    assert simulated_drafter(wet, plan, truth) == "reject"
    assert simulated_drafter({"room_id": "a", "action": "set_ceiling", "args": {"ceiling": 9.0}}, plan, truth) == "reject"


def test_approved_code_fixes_on_the_data():
    """End to end on data/: every approved fix lands on a planted error and puts the room where the truth has it."""
    truth = {r["id"]: r for h in load(DATA / "truth.json").values() for r in h["rooms"]}
    plans = {r["id"]: r for h in load(DATA / "ai_plan.json").values() for r in h["rooms"]}
    errors = {e["room_id"] for v in load(DATA / "answers.json").values() for e in v}
    fixed = defaultdict(list)
    for p in load(DATA / "proposals.json")["code"]:
        if p.get("decision") == "approve":
            assert p["room_id"] in errors and not p["field_was_right"]
            fixed[p["room_id"]].append(p)
    assert fixed
    for rid, ps in fixed.items():
        r = plans[rid]
        for p in ps:
            r = apply(r, p)
        t = truth[rid]
        assert abs(r["ceiling"] - t["ceiling"]) <= 0.5
        assert len(r["doors"]) == len(t["doors"]) and r["affected"] == t["affected"]
        slack = 0.03 * max(dims(t["polygon"])) + 0.1  # tour noise; a wrong anchor is off by the whole shift
        assert all(abs(a - b) <= slack for pa, pb in zip(r["polygon"], t["polygon"]) for a, b in zip(pa, pb))
        others = [o for o in truth.values() if o["id"] != rid and o["id"].split("-")[0] == rid.split("-")[0]]
        overlap = sum(Polygon(r["polygon"]).intersection(Polygon(o["polygon"])).area for o in others)
        assert overlap <= max(OVERLAP_MIN, 0.03 * Polygon(t["polygon"]).area)
