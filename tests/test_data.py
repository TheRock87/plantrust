"""v2 step 1: invariants of the generated data files (run src.generate and src.plant first)."""
import random
from collections import Counter

from src import generate
from src.common import DATA, N_HOUSES, SEED, dims, load
from src.plant import ERRORS

TRUTH, TOUR, PLAN, ANSWERS = (load(DATA / f) for f in ("truth.json", "tour.json", "ai_plan.json", "answers.json"))
EPS = 1e-9  # float slack on the range edges


def test_same_seed_same_house():
    a = generate.make_house(random.Random(SEED), 1)
    b = generate.make_house(random.Random(SEED), 1)
    assert a == b
    assert generate.make_tour(random.Random(SEED), a) == generate.make_tour(random.Random(SEED), b)


def test_door_cause_matches_miscount():
    for hid, house in TRUTH.items():
        for r in house["rooms"]:
            delta = TOUR[hid][r["id"]]["doors"] - len(r["doors"])
            assert r["door_cause"] == {1: "archway", -1: "hidden_door", 0: None}[delta]


def test_door_cause_hidden_from_plan_and_tour():
    # get_room and get_tour send these files to the model: the cause must come only from the notes.
    for f in ("ai_plan.json", "tour.json"):
        assert "door_cause" not in (DATA / f).read_text(encoding="utf-8")


def test_planted_errors():
    assert len(TRUTH) == N_HOUSES == 60
    truth = {r["id"]: r for h in TRUTH.values() for r in h["rooms"]}
    plan = {r["id"]: r for h in PLAN.values() for r in h["rooms"]}
    for key in ANSWERS.values():
        assert len(key) <= 3
        for e in key:
            t, p = truth[e["room_id"]], plan.get(e["room_id"])
            if e["code"] == "E6":
                assert t["affected"] and not p["affected"]
            if e["subtle"] and e["code"] == "E1":
                off = max(abs(a / b - 1) for a, b in zip(dims(p["polygon"]), dims(t["polygon"])))
                assert 0.04 - EPS <= off <= 0.06 + EPS
            if e["subtle"] and e["code"] == "E2":
                assert 0.7 - EPS <= abs(p["ceiling"] - t["ceiling"]) <= 1.0 + EPS
            assert not e["subtle"] or e["code"] in ("E1", "E2")
    codes = Counter(e["code"] for key in ANSWERS.values() for e in key)
    assert set(codes) == set(ERRORS)
    assert any(e["subtle"] for key in ANSWERS.values() for e in key)
