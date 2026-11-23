"""Shared paths, seed and small JSON helpers."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TRACES = ROOT / "traces"
SITE_DATA = ROOT / "site" / "data"

SEED = 2026
N_HOUSES = 40


def save(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True), encoding="utf-8")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dims(poly):
    """Width and depth of an axis-aligned rectangle given as 4 corner points."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return max(xs) - min(xs), max(ys) - min(ys)


def walls(poly):
    """Wall lengths in polygon order: bottom, right, top, left."""
    out = []
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        out.append(round(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5, 2))
    return out
