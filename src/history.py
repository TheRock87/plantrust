"""Part 2 data: about 150 made-up past mitigation jobs in one SQLite file (data/history.sqlite).

Each job is one water-damaged room with technician scope notes (like a voice-to-scope walkthrough) and
the line items an estimator wrote, in messy free text "by different estimators". The item codes are NOT
stored in job_items: the ingestion agent (src/ingest.py) has to work them out. The true codes are kept
apart in data/history_truth.json for scoring only.
"""
import math
import random
import sqlite3

from .common import DATA, SEED, save
from .cost import DOOR_HEIGHT_FT, fans_needed
from .prices import CATALOG, REGION_FACTOR, MockPriceSource

DB = DATA / "history.sqlite"
N_JOBS = 150
N_HOLDOUT_LINES = 100
N_HOLDOUT_JOBS = 20

ROOM_WEIGHTS = {"kitchen": 26, "bathroom": 26, "bedroom": 18, "living": 14, "hallway": 8, "closet": 4, "stairwell": 4}
FLOORS = {"kitchen": ["tile", "laminate", "vinyl"], "bathroom": ["tile", "vinyl"], "bedroom": ["carpet", "carpet", "hardwood"],
          "living": ["carpet", "hardwood", "laminate"], "hallway": ["carpet", "laminate"], "closet": ["carpet"],
          "stairwell": ["carpet"]}
SOURCES = {"kitchen": ["dishwasher supply line failed", "sink supply line burst", "refrigerator ice-maker line leaked"],
           "bathroom": ["toilet overflowed", "tub overflowed", "vanity supply line burst"],
           "other": ["pipe burst in the wall", "roof leak during a storm", "water heater failed in the next room"]}
FLOOR_NOTE = {"carpet": "Carpet and pad are soaked.", "laminate": "Laminate floor is cupping at the seams.",
              "vinyl": "Vinyl floor, water standing at the edges.", "tile": "Tile floor, water on the surface.",
              "hardwood": "Hardwood floor, boards starting to cup."}

# How estimators phrase each item. The catalog description itself is also used now and then.
VARIANTS = {
    "EQ-AIRM-DAY": ["air movers", "AM x 3 days", "fans / air movers per day", "set air mover", "drying fan rental"],
    "EQ-DEHU-DAY": ["dehu", "LGR dehumidifier", "dehumidifier per day", "dehu large 24hr"],
    "EQ-SCRUB-DAY": ["air scrubber", "HEPA scrubber per day", "negative air machine"],
    "MON-MOIST-DAY": ["moisture readings daily", "monitoring / mapping", "moisture map + monitor"],
    "LBR-TECH-HR": ["tech labor", "WTR technician hrs", "mitigation labor per hour"],
    "DRY-FLDCUT-LF": ["tear out wet sheetrock 2ft flood cut", "flood cut 2'", "flood cut drywall 24in", "cut drywall 2 ft up"],
    "DRY-RMV-SF": ["drywall removal - wet", "tear out wet drywall", "remove sheetrock full height", "demo wet gypsum board"],
    "INS-RMV-SF": ["remove wet insulation", "tear out batt insulation", "insulation demo"],
    "BSB-RMV-LF": ["remove baseboard", "tear out base trim", "baseboard R&R - remove only", "pull base"],
    "TRIM-CSG-RMV-LF": ["remove door casing", "pull casing", "door trim removal"],
    "DOR-DR-EA": ["detach & reset door", "pull door + reset", "door D&R"],
    "FLR-CRP-EXT-SF": ["extract water from carpet", "carpet extraction", "wtr extract carpet"],
    "FLR-CRP-RMV-SF": ["remove wet carpet", "tear out carpet", "carpet demo"],
    "FLR-PAD-RMV-SF": ["remove pad", "tear out carpet pad", "pad demo + bag"],
    "FLR-LAM-RMV-SF": ["remove laminate", "tear out laminate floor", "laminate demo"],
    "FLR-HARD-EXT-SF": ["extract water hard surface", "hard floor extraction", "wtr extract tile/vinyl"],
    "FLR-WOOD-MAT-DAY": ["floor drying mats", "wood floor drying system", "injectidry mats per day"],
    "STR-CRP-RMV-EA": ["remove stair carpet", "tear out carpet on steps", "stairs carpet demo per step"],
    "CLN-ANTI-SF": ["apply antimicrobial", "antimicrobial spray", "biocide application", "sanitize w/ antimicrobial"],
    "CLN-FINAL-SF": ["final clean", "clean up after mitigation", "final cleaning of room"],
    "PPE-EA": ["PPE", "tyvek suits + respirators", "protective gear per day"],
    "CNT-BARRIER-SF": ["containment", "poly barrier", "zip wall containment"],
    "CNT-MOVE-HR": ["content manipulation", "move furniture", "move out / block contents"],
    "CAB-TOE-RMV-LF": ["remove toe kick", "R&R toe kick", "pull cabinet toe kicks"],
    "CAB-DRILL-EA": ["drill cabinets for drying", "drill holes cab bases", "cabinet drilling"],
    "VAN-DR-EA": ["detach & reset vanity", "vanity D&R", "pull vanity for drying"],
    "PLM-TOILET-DR": ["detach & reset toilet", "pull toilet + reset", "toilet R&R", "toilet D&R"],
    "CLN-TOILET-EA": ["clean toilet seat", "sanitize toilet", "toilet clean"],
    "APP-DW-DR": ["detach & reset dishwasher", "pull dishwasher", "DW R&R"],
    "WIN-SCR-DR": ["window screens", "remove/reset screens", "screens D&R"],
    "HVAC-REG-CLN": ["clean registers", "HVAC vent cleaning", "clean floor register"],
}


def draw_job(rng, jid, room=None):
    room = room or rng.choices(list(ROOM_WEIGHTS), weights=list(ROOM_WEIGHTS.values()))[0]
    cat = rng.choices([1, 2, 3], weights=[45, 35, 20])[0]
    src_key = room if room in SOURCES else "other"
    source = rng.choice(SOURCES[src_key])
    if cat == 3:
        source = rng.choice(["sewer line backed up", "toilet overflowed with waste", "flood water came in from outside"])
    job = {
        "id": jid, "room_type": room, "loss_category": cat, "source": source,
        "floor": rng.choice(FLOORS[room]),
        "width": float(rng.randint(5 if room in ("closet", "hallway") else 8, 9 if room == "closet" else 20)),
        "depth": float(rng.randint(5, 9 if room in ("closet", "hallway", "stairwell") else 16)),
        "ceiling": 17.0 if room == "stairwell" else rng.choice([8.0, 8.0, 8.0, 9.0]),
        "doors": 1 if room in ("closet", "bathroom", "stairwell") else rng.choice([1, 2]),
        "cabinets_wet": room in ("kitchen", "bathroom") and rng.random() < 0.55,
        "windows": rng.randint(1, 3) if room in ("bedroom", "living") else (rng.randint(0, 1) if room == "kitchen" else 0),
        "registers": rng.randint(1, 2) if rng.random() < 0.6 else 0,
        "contents_heavy": rng.random() < {"bedroom": 0.7, "living": 0.7, "kitchen": 0.2}.get(room, 0.05),
        "region": rng.choice(sorted(REGION_FACTOR)),
        "month": f"2026-{rng.randint(1, 10):02d}",
    }
    return job


def quantities(job):
    """Every quantity basis an item can use, computed from the room size (code, not the model)."""
    w, d, c = job["width"], job["depth"], job["ceiling"]
    door_w = 3.0 * job["doors"]
    perim = 2 * (w + d)
    floor = w * d
    wet_wall = max(perim * (c - 2) - door_w * (DOOR_HEIGHT_FT - 2), 0)
    flood = perim - door_w
    cab = {"kitchen": (14, 6), "bathroom": (5, 2)}.get(job["room_type"], (0, 0))
    return {
        "floor_sf": round(floor, 1), "perimeter_lf": round(perim, 1), "flood_cut_lf": round(flood, 1),
        "wet_wall_sf": round(wet_wall, 1), "low_wall_sf": round(2 * flood, 1),
        "anti_sf": round(floor + 2 * flood, 1),
        "fan_days": fans_needed(floor, wet_wall) * 3, "dehu_days": math.ceil(floor * c / 1200) * 3,
        "days": 3, "tech_hours": 2 + math.ceil(floor / 60), "casing_lf": 17 * job["doors"], "doors": job["doors"],
        "steps": 14 if job["room_type"] == "stairwell" else 0, "ppe": 6, "barrier_sf": round(d * c, 1),
        "contents_hours": 2 if job.get("contents_heavy") else 1, "cabinet_lf": cab[0], "cabinets": cab[1],
        "one": 1, "windows": job.get("windows", 0), "registers": job.get("registers", 0),
    }


def true_items(rng, job):
    """What the estimator actually wrote: rules of thumb plus personal variation."""
    cat, room, floor = job["loss_category"], job["room_type"], job["floor"]
    p = {"EQ-AIRM-DAY": 0.97, "EQ-DEHU-DAY": 0.95, "MON-MOIST-DAY": 0.85, "LBR-TECH-HR": 0.8,
         "DRY-FLDCUT-LF": 0.6 if room == "closet" else 0.8, "BSB-RMV-LF": 0.85, "CLN-FINAL-SF": 0.6,
         "DRY-RMV-SF": 0.7 if cat == 3 else 0.3, "CLN-ANTI-SF": {1: 0.25, 2: 0.75, 3: 0.95}[cat],
         "PPE-EA": {1: 0.05, 2: 0.3, 3: 0.9}[cat], "EQ-SCRUB-DAY": {1: 0.05, 2: 0.25, 3: 0.8}[cat],
         "CNT-BARRIER-SF": 0.6 if cat == 3 else 0.05, "DOR-DR-EA": 0.25}
    if floor == "carpet":
        p.update({"FLR-CRP-EXT-SF": 0.9 if cat == 1 else 0.1, "FLR-CRP-RMV-SF": 0.15 if cat == 1 else 0.9,
                  "FLR-PAD-RMV-SF": 0.5 if cat == 1 else 0.9})
    elif floor == "laminate":
        p["FLR-LAM-RMV-SF"] = 0.85
    elif floor == "hardwood":
        p.update({"FLR-WOOD-MAT-DAY": 0.8, "FLR-HARD-EXT-SF": 0.6})
    else:
        p["FLR-HARD-EXT-SF"] = 0.85
    if room == "stairwell":
        p["STR-CRP-RMV-EA"] = 0.9
    if job["cabinets_wet"]:
        p.update({"CAB-TOE-RMV-LF": 0.85, "CAB-DRILL-EA": 0.7})
    if room == "bathroom":
        p.update({"PLM-TOILET-DR": 0.8 if cat == 3 else 0.55, "CLN-TOILET-EA": 0.5,
                  "VAN-DR-EA": 0.6 if job["cabinets_wet"] else 0.2})
    if room == "kitchen" and "dishwasher" in job["source"]:
        p["APP-DW-DR"] = 0.8
    if job["windows"]:
        p["WIN-SCR-DR"] = 0.55
    if job["registers"]:
        p["HVAC-REG-CLN"] = 0.6
    if job["contents_heavy"]:
        p["CNT-MOVE-HR"] = 0.75
    items = [code for code in sorted(p) if rng.random() < p[code]]
    if "DRY-FLDCUT-LF" in items:
        if rng.random() < 0.45:
            items.append("TRIM-CSG-RMV-LF")
        if cat >= 2 and rng.random() < 0.6:
            items.append("INS-RMV-SF")
    return sorted(set(items))


def scope_notes(rng, job, items):
    """Technician notes, as a voice-to-scope walkthrough would transcribe them. Some facts are left out."""
    s = [f"Category {job['loss_category']} water: {job['source']}.", FLOOR_NOTE[job["floor"]]]
    if "DRY-RMV-SF" in items:
        s.append("Drywall wet well above two feet, wicking high on the walls.")
    elif "DRY-FLDCUT-LF" in items:
        s.append(f"Drywall wet to about {rng.choice([10, 12, 14, 16, 18])} inches.")
    if job["cabinets_wet"]:
        s.append("Base cabinets are wet.")
    if job["windows"] and rng.random() < 0.7:
        s.append(f"{job['windows']} window{'s' if job['windows'] > 1 else ''} on the outside wall.")
    if job["registers"] and rng.random() < 0.6:
        s.append("Floor register in the wet area.")
    if job["contents_heavy"] and rng.random() < 0.7:
        s.append("Room is full of furniture.")
    if job["room_type"] == "stairwell":
        s.append("Carpeted stairs, water ran down from the landing.")
    if job["loss_category"] == 3:
        s.append("Strong odor; crew needs full protection.")
    return " ".join(s)


def messy(rng, code):
    """One estimator's wording of an item, with the usual noise."""
    r = rng.random()
    text = CATALOG[code][0] if r < 0.15 else rng.choice(VARIANTS[code])
    if rng.random() < 0.2:
        text = text.upper()
    if rng.random() < 0.15:
        words = text.split()
        i = rng.randrange(len(words))
        w = words[i]
        if len(w) > 4:
            j = rng.randrange(1, len(w) - 2)
            words[i] = w[:j] + w[j + 1] + w[j] + w[j + 2:]
        text = " ".join(words)
    if rng.random() < 0.1:
        text += rng.choice([" - per sf", " (bedroom)", " ***", " per estimator"])
    return text


def main():
    rng = random.Random(SEED * 5000)
    prices = MockPriceSource()
    jobs, lines, truth = [], [], {}
    for i in range(1, N_JOBS + 1):
        job = draw_job(rng, f"J{i:03d}")
        items = true_items(rng, job)
        job["notes"] = scope_notes(rng, job, items)
        q = quantities(job)
        for code in items:
            basis = CATALOG[code][2]
            line_id = len(lines) + 1
            unit_price = round(prices.get_price(code, job["region"], job["month"]) * rng.uniform(0.95, 1.05), 2)
            lines.append((line_id, job["id"], messy(rng, code), q[basis], unit_price))
            truth[line_id] = code
        jobs.append(job)

    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript("""
        CREATE TABLE catalog (code TEXT PRIMARY KEY, description TEXT, unit TEXT, basis TEXT,
                              example_price REAL, often_missed INTEGER);
        CREATE TABLE jobs (id TEXT PRIMARY KEY, room_type TEXT, loss_category INTEGER, source TEXT, floor TEXT,
                           width REAL, depth REAL, ceiling REAL, doors INTEGER, cabinets_wet INTEGER, windows INTEGER,
                           registers INTEGER, contents_heavy INTEGER, region TEXT, month TEXT, notes TEXT);
        CREATE TABLE job_items (id INTEGER PRIMARY KEY, job_id TEXT REFERENCES jobs(id), original_description TEXT,
                                quantity REAL, unit_price REAL, item_code TEXT, mapped_by TEXT);
    """)
    con.executemany("INSERT INTO catalog VALUES (?,?,?,?,?,?)",
                    [(c, d, u, b, p, int(m)) for c, (d, u, b, p, m) in sorted(CATALOG.items())])
    con.executemany("INSERT INTO jobs VALUES (:id,:room_type,:loss_category,:source,:floor,:width,:depth,:ceiling,"
                    ":doors,:cabinets_wet,:windows,:registers,:contents_heavy,:region,:month,:notes)", jobs)
    con.executemany("INSERT INTO job_items (id, job_id, original_description, quantity, unit_price) VALUES (?,?,?,?,?)",
                    lines)
    con.commit()
    con.close()

    hold = random.Random(SEED * 6000)
    save(DATA / "history_truth.json", {str(k): v for k, v in truth.items()})
    save(DATA / "history_holdout.json", {
        "ingest_lines": sorted(hold.sample(sorted(truth), N_HOLDOUT_LINES)),
        "estimate_jobs": sorted(hold.sample([j["id"] for j in jobs], N_HOLDOUT_JOBS)),
    })
    print(f"history: {len(jobs)} jobs, {len(lines)} line items -> {DB.name}")


if __name__ == "__main__":
    main()
