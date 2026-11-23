from src.checks import check_house


def room(rid, x0, x1, y0=0, y1=10, ceiling=8.0, doors=1, label="bedroom", flags=()):
    return {"id": rid, "label": label, "polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
            "ceiling": ceiling, "doors": [{"wall": 0, "width": 3.0}] * doors,
            "affected": True, "flags": list(flags)}


def tour_of(r, scale=1.0, ceiling=None, doors=None, label=None):
    (x0, y0), (x1, _), (_, y1) = r["polygon"][0], r["polygon"][1], r["polygon"][2]
    w, d = (x1 - x0) * scale, (y1 - y0) * scale
    return {"walls": [w, d, w, d], "ceiling": ceiling or r["ceiling"],
            "doors": len(r["doors"]) if doors is None else doors, "label": label or r["label"]}


def run(rooms, tour):
    return check_house({"rooms": rooms}, tour)


def test_clean_room_passes():
    a = room("a", 0, 10)
    assert run([a], {"a": tour_of(a, 1.01)})["a"]["status"] == "pass"


def test_wall_off_by_10_percent_fails():
    a = room("a", 0, 11)
    t = tour_of(a)
    t["walls"] = [10, 10, 10, 10]
    assert run([a], {"a": t})["a"]["status"] == "fail"


def test_wall_near_limit_is_unclear():
    a = room("a", 0, 10.4)
    t = tour_of(a)
    t["walls"] = [10, 10, 10, 10]
    assert run([a], {"a": t})["a"]["status"] == "unclear"


def test_ceiling_fails():
    a = room("a", 0, 10, ceiling=8)
    assert run([a], {"a": tour_of(a, ceiling=17)})["a"]["status"] == "fail"


def test_risk_flag_is_never_auto_accepted():
    a = room("a", 0, 10, ceiling=17, label="stairwell", flags=["stairs", "tall_ceiling"])
    assert run([a], {"a": tour_of(a)})["a"]["status"] == "unclear"


def test_overlap_is_found_on_both_rooms():
    a, b = room("a", 0, 11.5), room("b", 10, 20)
    out = run([a, b], {"a": tour_of(a), "b": tour_of(b)})
    assert out["a"]["numbers"]["overlaps"][0]["other"] == "b"
    assert out["b"]["status"] == "unclear"


def test_missing_room_fails():
    a, b = room("a", 0, 10), room("b", 10, 20)
    out = run([a], {"a": tour_of(a), "b": tour_of(b)})
    assert out["b"]["status"] == "fail" and out["b"]["missing"]
