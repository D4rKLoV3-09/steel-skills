#!/usr/bin/env python3
"""SJII: read every steel GA plan (vector PDF, 1:200) -> plan_members.json (mm, per sheet).

    python models/sjii/read_plans.py OUT.json

Reading functions: generate-model/ga_plan.py. Per sheet: black member lines 0.9-1.4 pt wide (straight; arcs flattened into chords) paired with the
steel mark text beside them (parallel, within the line, <= 9 pt off); slab labels "<thk> BDK";
grid bubbles -> calibration (1:200 = 70.556 mm/pt, anchored on one bubble per axis).
Frames: CTB grid A1.. (X) / AA.. (Y); EDU (ES + HS sheets share grid B7) B1.. (X) / BA.. (Y).
"""
import json
import math
import re
import sys
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "generate-model"))
import ga_plan as gp  # noqa: E402

DIR = Path(__file__).resolve().parents[2] / "jobs" / "SJII" / "Drawings" / "Steel Structure Drawings"
MMPT = 25.4 / 72 * 200
MARK = re.compile(r"^(B\d{2,3}[A-Z]{1,2}|R20A|C3\d[A-Z]{1,2}|BU\d\d|S[235]0[A-Z]|D40H|SC01)$")
# FFL (m) from the architectural sections SJI-DPA-ZZ-XX-DR-A-2001 (CTB) and SJII-DPA-ES / HS-XX-DR-A-2001 (EDU)
CTB = {"01": 8.70, "02": 15.00, "03": 20.25, "04": 28.10, "05": 33.35, "06": 38.60, "LR": 43.85, "UR": 49.10}
EDU = {"01": 9.75, "02": 15.00, "03": 20.25, "04": 25.50, "05": 30.00, "06": 34.50, "07": 39.00, "08": 43.50,
       "09": 48.00, "10": 52.50, "LR": 57.00, "UR": 63.50}
# grid positions (mm) - all bays 9000 as dimensioned, BM-BN 4500
GX = {**{f"A{i}": (i - 1) * 9000 for i in range(1, 13)}, **{f"B{i}": (i - 1) * 9000 for i in range(1, 19)}}
GY = {**{f"A{c}": i * 9000 for i, c in enumerate("ABCDEFGHJ")}}
_y = 0
for c in "ABCDEFGHJKLMNPQR":
    GY["B" + c] = _y
    _y += 4500 if c == "M" else 9000


def sheets():
    for f in sorted(DIR.glob("SJI-ARP-*-DR-S-2*-T1.pdf")):
        m = re.match(r"SJI-ARP-(CTB|ES|HS)-(\w\w)-DR", f.name)
        if not m:
            continue
        b, lv = m.groups()
        tab = CTB if b == "CTB" else EDU
        if lv in tab:
            yield b, lv, tab[lv], f


WMIN, WMAX = 0.9, 1.4      # beams 0.96 or 1.32 pt (columns / walls 1.32 stay unlabelled)


def read(b, lv, ffl, f):
    page = fitz.open(f)[0]
    words = page.get_text("words")
    pat = r"^A(\d{1,2}|[A-J])$" if b == "CTB" else r"^B(\d{1,2}|[A-R])$"
    bub = {}
    for w in words:
        if re.match(pat, w[4]) and (w[2] - w[0]) < 45:
            bub.setdefault(w[4], ((w[0] + w[2]) / 2, (w[1] + w[3]) / 2))
    xs = {k: v[0] for k, v in bub.items() if k in GX}
    ys = {k: v[1] for k, v in bub.items() if k in GY}
    kx = "B7" if "B7" in xs else ("A1" if b == "CTB" else min(xs, key=lambda k: GX[k]))
    ky = min(ys, key=lambda k: GY[k])
    # check every other bubble against the 9000 grid (flags a wrong scale / grid)
    err = max([abs(GX[kx] + (xs[k] - xs[kx]) * MMPT - GX[k]) for k in xs if k != "A9"] +
              [abs(GY[ky] + (ys[ky] - ys[k]) * MMPT - GY[k]) for k in ys])
    X = lambda px: round(GX[kx] + (px - xs[kx]) * MMPT, 1)
    Y = lambda py: round(GY[ky] + (ys[ky] - py) * MMPT, 1)
    # plan area: inside the grid bubbles, left of the schedules
    region = (min(xs.values()) - 220, min(ys.values()) - 220, min(max(xs.values()) + 260, 2680), max(ys.values()) + 60)
    lines = [m for m in gp.merge(page, region, WMIN, WMAX) if math.hypot(m[2] - m[0], m[3] - m[1]) > 2]
    ch = gp.chains(lines)
    paired, loose, used = gp.pair(lines, ch, gp.labels(page, region, MARK), gp.arcs(page, region, WMIN, WMAX))
    mem = []
    for m in paired:
        P = [[X(x), Y(y)] for x, y in m["pts"]]
        for p, q in zip(P, P[1:]):
            mem.append({"mark": m["mark"], "a": p, "b": q, **({"arc": True} if len(P) > 2 else {})})
    free = [{"mark": t, "at": [X(x), Y(y)]} for t, x, y in loose]
    # slab thickness labels "<thk>" directly above "BDK"
    bdk = []
    for w in words:
        if w[4] == "BDK" and region[0] < w[0] < region[2] and region[1] < w[1] < region[3]:
            for v in words:
                if re.match(r"^\d{3}$", v[4]) and abs((v[0] + v[2]) / 2 - (w[0] + w[2]) / 2) < 8 and 0 < w[1] - v[3] < 6:
                    bdk.append({"thk": int(v[4]), "at": [X((w[0] + w[2]) / 2), Y(w[1])]})
    cols = [{"c": [X(c["c"][0]), Y(c["c"][1])], "s": [round(c["s"][0] * MMPT), round(c["s"][1] * MMPT)], "fill": c["fill"],
             "round": c["round"]} for c in gp.outlines(page, region)]
    unl = [i for i in range(len(lines)) if ch[i] not in used]
    print(f"{b}-{lv} FFL {ffl:.2f}: {len(mem)} members, {len(free)} unpaired marks, {len({ch[i] for i in unl})} unlabelled lines, "
          f"{len(bdk)} BDK labels, {len(cols)} column outlines ({sum(c['round'] for c in cols)} round), grid check {err:.0f} mm")
    return {"bldg": b, "lv": lv, "ffl": ffl, "sheet": f.stem, "members": mem, "free": free, "bdk": bdk, "cols": cols,
            "unlabelled": [[X(lines[i][0]), Y(lines[i][1]), X(lines[i][2]), Y(lines[i][3])] for i in unl]}



if __name__ == "__main__":
    out = [read(*s) for s in sheets()]
    json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), indent=0)
