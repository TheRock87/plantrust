"""Cost at risk per room, from two illustrative mitigation items (not real price lists).

1. Wet drywall removal: wall area above 2 ft x 1.20 USD per sq ft.
2. Drying fans (air movers): 1 per affected room + 1 per 50 sq ft of wet floor (round up)
   + 1 per 100 sq ft of wet wall above 2 ft (round up); 30 USD per fan per day for 3 days.
Simplification: in an affected room the whole wall above 2 ft is treated as wet.
"""
import math

from .common import dims

DRYWALL_USD_PER_SQFT = 1.20
FAN_USD_PER_DAY = 30
DRYING_DAYS = 3
DOOR_HEIGHT_FT = 6.67
TOUR_DOOR_WIDTH_FT = 3.0  # the tour counts doors but does not measure their width


def _up(x):
    return math.ceil(x - 1e-9)


def fans_needed(floor_sqft, wet_wall_sqft):
    return 1 + _up(floor_sqft / 50) + _up(wet_wall_sqft / 100)


def cost_from_dims(width, depth, ceiling, door_widths, affected):
    if not affected:
        return {"floor": 0.0, "wall": 0.0, "fans": 0, "usd": 0.0}
    floor = width * depth
    wall = 2 * (width + depth) * max(ceiling - 2, 0) - sum(w * (DOOR_HEIGHT_FT - 2) for w in door_widths)
    wall = max(wall, 0.0)
    fans = fans_needed(floor, wall)
    usd = wall * DRYWALL_USD_PER_SQFT + fans * FAN_USD_PER_DAY * DRYING_DAYS
    return {"floor": round(floor, 1), "wall": round(wall, 1), "fans": fans, "usd": round(usd, 2)}


def room_cost(room):
    """Cost of a plan or truth room."""
    w, d = dims(room["polygon"])
    return cost_from_dims(w, d, room["ceiling"], [x["width"] for x in room["doors"]], room["affected"])


def tour_cost(tour_room, affected):
    """Cost implied by the tour measurements (average of opposite walls)."""
    w0, w1, w2, w3 = tour_room["walls"]
    return cost_from_dims((w0 + w2) / 2, (w1 + w3) / 2, tour_room["ceiling"],
                          [TOUR_DOOR_WIDTH_FT] * tour_room["doors"], affected)
