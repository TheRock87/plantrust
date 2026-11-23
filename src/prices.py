"""Price source for the estimation agent.

In production, prices come from Xactimate through the company's existing Verisk integration. This demo
uses MockPriceSource: a made-up catalog of generic mitigation items with OWN codes and example prices.
The agents do not change between the two; only the price source does.
"""
from typing import Protocol

# code: (description, unit, quantity basis, example price USD, often missed)
CATALOG = {
    "EQ-AIRM-DAY": ("Air mover, per 24 hour period", "EA-DAY", "fan_days", 30.00, False),
    "EQ-DEHU-DAY": ("Dehumidifier, large, per 24 hour period", "EA-DAY", "dehu_days", 75.00, False),
    "EQ-SCRUB-DAY": ("Air scrubber, per 24 hour period", "EA-DAY", "days", 70.00, False),
    "MON-MOIST-DAY": ("Moisture monitoring and mapping, per day", "DAY", "days", 45.00, False),
    "LBR-TECH-HR": ("Water mitigation technician, per hour", "HR", "tech_hours", 62.00, False),
    "DRY-FLDCUT-LF": ("Flood cut wet drywall 2 ft, per LF", "LF", "flood_cut_lf", 3.10, False),
    "DRY-RMV-SF": ("Remove wet drywall, per SF", "SF", "wet_wall_sf", 1.20, False),
    "INS-RMV-SF": ("Remove wet wall insulation, per SF", "SF", "low_wall_sf", 0.85, False),
    "BSB-RMV-LF": ("Remove baseboard, per LF", "LF", "perimeter_lf", 1.10, False),
    "TRIM-CSG-RMV-LF": ("Remove door casing, per LF", "LF", "casing_lf", 1.30, True),
    "DOR-DR-EA": ("Detach and reset interior door", "EA", "doors", 38.00, False),
    "FLR-CRP-EXT-SF": ("Water extraction from carpet, per SF", "SF", "floor_sf", 0.45, False),
    "FLR-CRP-RMV-SF": ("Remove wet carpet, per SF", "SF", "floor_sf", 0.40, False),
    "FLR-PAD-RMV-SF": ("Remove wet carpet pad, per SF", "SF", "floor_sf", 0.35, False),
    "FLR-LAM-RMV-SF": ("Remove laminate flooring, per SF", "SF", "floor_sf", 1.25, False),
    "FLR-HARD-EXT-SF": ("Water extraction from hard surface floor, per SF", "SF", "floor_sf", 0.30, False),
    "FLR-WOOD-MAT-DAY": ("Hardwood floor drying mat system, per day", "DAY", "days", 95.00, False),
    "STR-CRP-RMV-EA": ("Remove carpet from stairs, per step", "EA", "steps", 9.00, False),
    "CLN-ANTI-SF": ("Apply antimicrobial agent, per SF", "SF", "anti_sf", 0.28, False),
    "CLN-FINAL-SF": ("Final cleaning, per SF", "SF", "floor_sf", 0.20, False),
    "PPE-EA": ("Personal protective equipment, per person per day", "EA", "ppe", 14.00, False),
    "CNT-BARRIER-SF": ("Containment barrier, plastic sheeting, per SF", "SF", "barrier_sf", 0.90, False),
    "CNT-MOVE-HR": ("Move and block room contents, per hour", "HR", "contents_hours", 55.00, True),
    "CAB-TOE-RMV-LF": ("Detach cabinet toe kick, per LF", "LF", "cabinet_lf", 4.50, False),
    "CAB-DRILL-EA": ("Drill cabinet bases for drying, per cabinet", "EA", "cabinets", 12.00, False),
    "VAN-DR-EA": ("Detach and reset vanity", "EA", "one", 140.00, False),
    "PLM-TOILET-DR": ("Detach and reset toilet", "EA", "one", 185.00, False),
    "CLN-TOILET-EA": ("Clean and sanitize toilet seat and bowl", "EA", "one", 22.00, True),
    "APP-DW-DR": ("Detach and reset dishwasher", "EA", "one", 120.00, False),
    "WIN-SCR-DR": ("Detach and reset window screen", "EA", "windows", 9.50, True),
    "HVAC-REG-CLN": ("Clean heating and cooling register", "EA", "registers", 11.00, True),
}

REGION_FACTOR = {"FL-TAMPA": 1.00, "TX-DALLAS": 0.96, "IL-CHICAGO": 1.08, "CA-SACRAMENTO": 1.14}
MONTHLY_DRIFT = 0.003  # example price drift per month from 2026-01


class PriceSource(Protocol):
    def get_price(self, item_code: str, region: str, month: str) -> float: ...


class MockPriceSource:
    """Example prices for the demo. Not a real price list."""

    def get_price(self, item_code, region, month):
        base = CATALOG[item_code][3]
        months = (int(month[:4]) - 2026) * 12 + int(month[5:7]) - 1
        return round(base * REGION_FACTOR.get(region, 1.0) * (1 + MONTHLY_DRIFT * months), 2)


class XactimatePriceSource:
    """Production price source: NOT implemented here.

    It needs the company's existing Verisk/Xactimate integration and a licensed regional price list.
    Xactimate prices and item codes are licensed for the subscriber's internal use and may not be
    redistributed, so this demo neither uses nor imitates them. The estimation agent would call this
    class unchanged in place of MockPriceSource, mapping the catalog codes above to the licensed codes.
    """

    def get_price(self, item_code, region, month):
        raise NotImplementedError("Requires the production Verisk/Xactimate integration and a licensed price list.")
