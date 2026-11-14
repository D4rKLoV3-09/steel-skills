#!/usr/bin/env python3
"""SJII: truss elevations S-8101 (CTB1-3) and S-8201 (ES1, ES1a, HS1), 1:50 -> truss_types.json.

    python models/sjii/read_trusses.py OUT.json

Members are drawn as outlines. Chords: edges and marks set below (read from the long horizontal lines; chords of
CTB1 / CTB2 lie flat = web horizontal, drawn width = flange width). Verticals and diagonals: ga_plan.bands pairs
the outline lines, each band takes the nearest parallel mark. Local mm: x along the truss from the middle of the
top chord, z down from the top of the top chord (negative).
Assumed where the sheet says nothing: CTB2 chords carry no mark (drawn 421 wide = BU09); HS1 bottom chord carries
no mark (drawn as C35W); HS1 top chord is labelled B61T | C35W | B61T although drawn 419 deep - labels followed.
"""
import json
import math
import re
import sys
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "generate-model"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ga_plan as gp  # noqa: E402
from sections import lookup  # noqa: E402

DIR = Path(__file__).resolve().parents[2] / "jobs" / "SJII" / "Drawings" / "Steel Structure Drawings"
CTB, EDU = "SJI-ARP-CTB-ZZ-DR-S-8101-T1.pdf", "SJI-ARP-EDU-ZZ-DR-S-8201-T1.pdf"
K = 25.4 / 72 * 50                       # mm per pt at 1:50
WEB = re.compile(r"^(C3\d[A-Z]{1,2}|BU\d\d|S[235]0[A-Z])$")
# chords: (mark, x0, x1, y top edge, y bottom edge, flat) in PDF points
VIEWS = {
    "CTB1": dict(pdf=CTB, region=(176, 300, 2520, 625), tc=[("C35FF", 239, 2437, 340.9, 365.4, True)],
                 bc=[("C35CC", 342, 2368, 470.8, 494.9, True)], assumed=[]),
    "CTB2": dict(pdf=CTB, region=(208, 880, 1420, 1140), tc=[("BU09", 338, 1312, 927.7, 951.6, True)],
                 bc=[("BU09", 338, 1312, 1044.0, 1067.9, True)], assumed=["tc", "bc"]),
    "CTB3": dict(pdf=CTB, region=(1650, 890, 2360, 1125), tc=[("C35FF", 1748, 2213, 927.75, 956.05, False)],
                 bc=[("C35FF", 1748, 2213, 1052.45, 1080.75, False)], assumed=[]),
    "ES1": dict(pdf=EDU, region=(300, 185, 1900, 420), tc=[("C35Z", 352, 1859, 216.4, 241.2, False)],
                bc=[("C35Z", 360, 1859, 301.4, 326.2, False)], assumed=[]),
    "ES1a": dict(pdf=EDU, region=(300, 635, 1990, 870),
                 tc=[("C35W", a, b, 665.6, 689.4, False) for a, b in ((342, 833), (861, 1343), (1372, 1844))],
                 bc=[("C35W", a, b, 750.7, 774.5, False) for a, b in ((360, 824), (870, 1334), (1381, 1844))], assumed=[]),
    "HS1": dict(pdf=EDU, region=(340, 1065, 1870, 1250),
                tc=[("B61T", 351, 1070, 1090.0, 1113.7, False), ("C35W", 1070, 1139, 1090.0, 1113.7, False),
                    ("B61T", 1139, 1858, 1090.0, 1113.7, False)],
                bc=[("C35W", 360, 1849, 1174.9, 1198.7, False)], assumed=["bc"]),
}


def read(name, v):
    page = fitz.open(DIR / v["pdf"])[0]
    reg = v["region"]
    lines = [m for m in gp.merge(page, reg, 0.0, 5.0, gap=1.0) if math.hypot(m[2] - m[0], m[3] - m[1]) > 6]
    lab = gp.labels(page, reg, WEB)
    x0, x1 = min(c[1] for c in v["tc"]), max(c[2] for c in v["tc"])
    ytop, ytc, ybc, ybot = v["tc"][0][3], (v["tc"][0][3] + v["tc"][0][4]) / 2, (v["bc"][0][3] + v["bc"][0][4]) / 2, v["bc"][0][4]
    clear = v["bc"][0][3] - v["tc"][0][4]
    X, Z = lambda px: round((px - (x0 + x1) / 2) * K, 1), lambda py: round((ytop - py) * K, 1)

    def mark(b):
        """Nearest mark parallel to the band, within 30 pt of its centre line."""
        ax, ay, bx, by = *b["a"], *b["b"]
        L = math.dist(b["a"], b["b"])
        t = ((bx - ax) / L, (by - ay) / L)
        best = None
        for txt, cx, cy, d in lab:
            s = max(0, min(L, (cx - ax) * t[0] + (cy - ay) * t[1]))
            dist = math.hypot(cx - ax - s * t[0], cy - ay - s * t[1]) + (0 if abs(t[0] * d[0] + t[1] * d[1]) > 0.9 else 15)
            if dist < 30 and (best is None or dist < best[0]):
                best = (dist, txt)
        return best[1] if best else None
    vs, ds, kg = [], [], 0.0
    for b in gp.bands(lines):
        cx, cy = (b["a"][0] + b["b"][0]) / 2, (b["a"][1] + b["b"][1]) / 2
        L = math.dist(b["a"], b["b"])
        if not (8 <= b["w"] <= 30 and x0 - 2 <= cx <= x1 + 2):
            continue
        if abs(abs(b["ang"]) - 90) < 1 and L >= 0.7 * clear and min(b["a"][1], b["b"][1]) >= ytop - 3 and max(b["a"][1], b["b"][1]) <= ybot + 3:
            vs.append({"mark": mark(b), "px": cx, "len": clear * K})
        elif 8 < abs(b["ang"]) < 82 and ytop < cy < ybot:
            tx, ty = math.cos(math.radians(b["ang"])), math.sin(math.radians(b["ang"]))
            ds.append({"mark": mark(b), "pt": cx + (ytc - cy) * tx / ty, "pb": cx + (ybc - cy) * tx / ty, "len": L * K})
    vs.sort(key=lambda m: m["px"])
    for d in ds:                                   # concentric with a vertical when within 250 mm of its centre line
        for e in ("pt", "pb"):
            near = min(vs, key=lambda m: abs(m["px"] - d[e]), default=None)
            if near and abs(near["px"] - d[e]) * K < 250:
                d[e] = near["px"]
    ds.sort(key=lambda m: m["pt"] + m["pb"])
    unmarked = [m for m in vs + ds if not m["mark"]]
    chord = lambda c: {"mark": c[0], "x0": X(c[1]), "x1": X(c[2]), "z": Z((c[3] + c[4]) / 2), "flat": c[5]}
    out = {"len": round((x1 - x0) * K), "tc": [chord(c) for c in v["tc"]], "bc": [chord(c) for c in v["bc"]],
           "v": [{"mark": m["mark"], "x": X(m["px"])} for m in vs if m["mark"]],
           "d": [{"mark": m["mark"], "xt": X(m["pt"]), "xb": X(m["pb"])} for m in ds if m["mark"]],
           "assumed": v["assumed"], "sheet": v["pdf"][:-4]}
    kg = sum(lookup(c[0])["kgm"] * (c[2] - c[1]) * K / 1000 for c in v["tc"] + v["bc"]) + sum(lookup(m["mark"])["kgm"] * m["len"] / 1000 for m in vs + ds if m["mark"])
    print(f"{name}: {out['len'] / 1000:.1f} m long, {-out['bc'][0]['z'] / 1000:.2f} m top of steel to bottom chord centre, {len(out['tc'])} + {len(out['bc'])} chord pieces, "
          f"{len(out['v'])} verticals, {len(out['d'])} diagonals, {len(unmarked)} bands without a mark, about {kg / 1000:.1f} t")
    return out


if __name__ == "__main__":
    json.dump({n: read(n, v) for n, v in VIEWS.items()}, open(sys.argv[1], "w", encoding="utf-8"), indent=0)
