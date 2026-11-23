from src.cost import cost_from_dims, fans_needed


def test_brief_example_floor_fans():
    # 22 x 22 ft = 484 sq ft; 484 / 50 = 9.68, rounded up = 10 fans for the floor part
    assert fans_needed(484, 0) - 1 == 10


def test_affected_room_cost():
    c = cost_from_dims(10, 12, 8, [3.0], True)
    # wall above 2 ft: 44 ft perimeter x 6 ft = 264, minus door 3 x 4.67 = 14.01 -> 249.99
    assert abs(c["wall"] - 250.0) < 0.1
    # fans: 1 room + ceil(120/50)=3 + ceil(249.99/100)=3 -> 7
    assert c["fans"] == 7
    assert abs(c["usd"] - (249.99 * 1.2 + 7 * 30 * 3)) < 0.1


def test_unaffected_room_costs_nothing():
    assert cost_from_dims(10, 12, 8, [], False)["usd"] == 0


def test_ceiling_error_changes_cost():
    low = cost_from_dims(12, 12, 8, [], True)["usd"]
    high = cost_from_dims(12, 12, 17, [], True)["usd"]
    assert high - low > 300
