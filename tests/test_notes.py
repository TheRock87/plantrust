"""v2 step 2: technician notes (data/notes.json) and the hand-written hard set (data/notes_hard.json)."""
from src import notes
from src.common import DATA, load

TRUTH = load(DATA / "truth.json")
ROOMS = {r["id"]: r for h in TRUTH.values() for r in h["rooms"]}


def test_seeded_and_file_is_current():
    a, _ = notes.build(TRUTH)
    b, _ = notes.build(TRUTH)
    assert a == b == load(DATA / "notes.json")


def test_one_to_three_sentences_per_room():
    built, _ = notes.build(TRUTH)
    assert set(built) == set(ROOMS)
    for text in built.values():
        assert 1 <= text.count(".") <= 3, text  # every sentence ends with one full stop


def test_facts_agree_with_truth():
    _, kinds = notes.build(TRUTH)
    for rid, ks in kinds.items():
        r = ROOMS[rid]
        assert ("wet" in ks) <= r["affected"]
        assert ("dry" in ks) <= (not r["affected"])
        assert ("neighbour" in ks) <= (not r["affected"])  # only a dry room talks about a wet neighbour
        assert ("archway" in ks) <= (r["door_cause"] == "archway")
        assert ("hidden_door" in ks) <= (r["door_cause"] == "hidden_door")
    wet = [rid for rid, r in ROOMS.items() if r["affected"]]
    share = sum("wet" in kinds[rid] for rid in wet) / len(wet)
    assert 0.75 <= share <= 0.95  # brief: wet rooms mentioned about 85 % of the time


def test_hard_set():
    cases = load(DATA / "notes_hard.json")
    assert 15 <= len(cases) <= 20
    assert len({c["id"] for c in cases}) == len(cases)
    for c in cases:
        assert c["question"] in ("wet", "door")
        assert c["expected"] in ("mark_wet", "add_door", "no_change", "ask_drafter")
        if c["question"] == "wet":  # routed to the agent: plan says not wet and the room has a note
            assert not c["plan_affected"] and c["expected"] in ("mark_wet", "no_change", "ask_drafter")
        else:  # routed to the agent: door counts differ
            assert c["plan_doors"] != c["tour_doors"] and c["expected"] in ("add_door", "no_change", "ask_drafter")
        assert c["note"] and c["why"]
