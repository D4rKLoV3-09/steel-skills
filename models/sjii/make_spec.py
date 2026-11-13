#!/usr/bin/env python3
"""SJII (St. Joseph's Institution International): plan_members.json -> spec.json for geometry.py.

    python models/sjii/make_spec.py models/sjii/plan_members.json OUT_SPEC.json OUT_EXTRA.json

Source: Arup tender GA plans (T1, 30/10/26) for the Central Block (CTB 2101-2108), Education ES (2221-2229)
and HS (2321-2332), read by read_plans.py. FFL from the architectural sections; TOS = FFL - slab 150 (ASSUMED).
Frames: EDU (ES + HS) X from grid B1, Y from BA; CTB X from A1 + 200 m, Y from AA - 120 m (shown beside EDU, not in
site position). Z absolute mm.

Per floor: every marked beam line (curved beams as chords); the plans draw the lines short of each other, so every
end runs to its neighbour (ga_plan.connect): column face, crossing beam axis (coped), or the beam in line (butt).
Cautious joints (big member on a small support) and ends with no neighbour within 1.5 m go to EXTRA.
Steel columns: marks D40H / SC01 without a line -> column from the floor below to this floor's TOS.
Bondek package (ga_plan.bondek; ASSUMED Bondek II 1.0 BMT, studs 19x100 @300, edgeform 1.2 BMT x slab).
EXTRA = ghosts (RC columns, round where drawn round), cautions, per-floor deck m2 / edgeform m, counts.

Rebuild everything (page + MTO + checks): python models/sjii/build.py   (add --read after a drawing change)
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "generate-model"))
import ga_plan as gp  # noqa: E402
from sections import SCHED, lookup  # noqa: E402

SLAB = 150                 # "150 BDK" on the plans
CTB_DX, CTB_DY = 200000, -120000   # CTB drawn beside EDU (own grid frame, not site position)
COLMARK = {"D40H", "SC01"}
BLD = {"CTB": "Central Block", "ES": "Education ES", "HS": "Education HS"}

sheets = json.load(open(sys.argv[1], encoding="utf-8"))
profiles, members, extra = {}, [], {"ghosts": [], "floors": {}, "skipped": {}, "free_marks": {}, "cautions": [], "open": []}


def prof(mark):
    name = SCHED[mark]
    if name not in profiles:
        r = lookup(mark)
        p = {k: r[k] for k in ("type", "h", "b", "d", "tw", "tf", "t", "kgm") if k in r}
        profiles[name] = p
        extra.setdefault("prof_info", {})[name] = r
    return name


def depth(name):
    p = profiles[name]
    return p.get("h", p.get("d", p.get("b")))


# EDU floors: ES + HS sheets of one level form one floor (they share grid B7); CTB floors on their own
floors = {}
for s in sheets:
    key = ("CTB" if s["bldg"] == "CTB" else "EDU", s["lv"])
    floors.setdefault(key, []).append(s)
LEVELS = {}
for (fr, lv), ss in floors.items():
    LEVELS.setdefault(fr, []).append((ss[0]["ffl"], lv))
for fr in LEVELS:
    LEVELS[fr].sort()


def below(fr, lv):
    lv_list = LEVELS[fr]
    i = [l for _, l in lv_list].index(lv)
    return lv_list[i - 1][0] if i else None


uid = 0
for (fr, lv), ss in sorted(floors.items()):
    ffl = ss[0]["ffl"]
    tos = round(ffl * 1000 - SLAB)
    dx, dy = (CTB_DX, CTB_DY) if fr == "CTB" else (0, 0)
    beams, cols, lines = [], [], []
    seen = set()
    for s in ss:
        bl = s["bldg"]
        for c in s["cols"]:
            cols.append({"c": [c["c"][0] + dx, c["c"][1] + dy], "s": c["s"], "fill": c["fill"], "round": c["round"]})
        for m in s["members"]:
            a = [round(m["a"][0] + dx), round(m["a"][1] + dy)]
            b = [round(m["b"][0] + dx), round(m["b"][1] + dy)]
            if math.dist(a, b) < 150:
                continue
            k = tuple(sorted([(round(a[0] / 100), round(a[1] / 100)), (round(b[0] / 100), round(b[1] / 100))]))
            if k in seen:                       # ES / HS overlap on grid B7
                continue
            seen.add(k)
            beams.append({"mark": m["mark"], "a": a, "b": b, "arc": m.get("arc", False), "bldg": bl, "sheet": s["sheet"]})
        lines += [(u[0] + dx, u[1] + dy, u[2] + dx, u[3] + dy) for u in s["unlabelled"]]
        for f in s["free"]:
            extra["free_marks"].setdefault(f["mark"], []).append(f"{bl}-{lv}")
    zb = below(fr, lv)
    z0 = round(zb * 1000 - SLAB) if zb else tos - 4500
    # ---- steel columns at their marks (D40H / SC01), on the nearest drawn outline ----
    steel_cols = []
    for s in ss:
        for f in s["free"]:
            if f["mark"] not in COLMARK:
                continue
            at = [f["at"][0] + dx, f["at"][1] + dy]
            near = min(cols, key=lambda c: math.dist(c["c"], at), default=None)
            p = near["c"] if near and math.dist(near["c"], at) < 1500 else at
            if any(math.dist(q, p) < 200 for q, *_ in steel_cols):
                continue
            steel_cols.append((p, f["mark"], s))
    # ---- RC column ghosts from the floor below (concrete by others), in the drawn shape ----
    seenc = []
    for c in cols:
        if any(math.dist(c["c"], q) < 300 for q in seenc) or any(math.dist(c["c"], q) < 300 for q, *_ in steel_cols):
            continue
        seenc.append(c["c"])
        if c["fill"] or max(c["s"]) >= 450:
            extra["ghosts"].append({"n": "RC column (by others)", "c": [c["c"][0], c["c"][1], (z0 + tos) / 2],
                                    "s": [c["s"][0], c["s"][1], tos - z0], **({"r": c["s"][0] / 2} if c["round"] else {})})
    # ---- beam ends: every end runs to its neighbour (ga_plan.connect) ----
    for i, bm in enumerate(beams):
        bm["id"] = f"{fr}-{lv}-{i}"
        bm["prof"] = prof(bm["mark"])
    cautions, opened = gp.connect(beams, cols, profiles, lines)
    byid = {bm["id"]: bm for bm in beams}
    for c in cautions:
        bm = byid[c["bm"]]
        o = byid[c["on"]] if "on" in c else None
        extra["cautions"].append({"k": c["k"], "id": c["bm"], "floor": f"{fr}-{lv}", "bldg": bm["bldg"], "sheet": bm["sheet"], "mark": bm["mark"],
                                  "on": o["mark"] if o else "column %d wide" % min(c["col"]["s"])})
    extra["open"] += [f"{i} ({byid[i]['mark']})" for i in opened]
    for bm in beams:
        if math.dist(bm["a"], bm["b"]) < 100:
            extra["skipped"].setdefault("too short after joining", []).append(bm["id"])
            continue
        zc = tos - depth(bm["prof"]) / 2
        members.append({"id": bm["id"], "ref": bm["mark"], "prof": bm["prof"], "a": [*bm["a"], zc], "b": [*bm["b"], zc],
                        "up": [0, 0, 1], "rank": 2, "ends": bm["ends"], "layer": "beam", "floor": f"{fr}-{lv}",
                        "bldg": bm["bldg"], "src": f"{bm['sheet']} ({bm['mark']} {SCHED[bm['mark']]}); TOS {tos / 1000:+.3f} = FFL - {SLAB}",
                        "end_kind": bm["end_kind"], "tos": tos})
    for p, mark, s in steel_cols:
        members.append({"id": f"{fr}-{lv}-col{len(members)}", "ref": mark, "prof": prof(mark), "a": [p[0], p[1], z0],
                        "b": [p[0], p[1], tos - 0.0], "up": [1, 0, 0], "rank": 0, "ends": [None, None], "layer": "col",
                        "floor": f"{fr}-{lv}", "bldg": s["bldg"], "tos": tos,
                        "src": f"{s['sheet']} ({mark} {SCHED[mark]} at the mark); from the floor below "
                               f"({z0 / 1000:+.3f}) to TOS {tos / 1000:+.3f} - ASSUMED storey"})
    # ---- bondek package ----
    fl = [m for m in members if m["floor"] == f"{fr}-{lv}" and m["layer"] == "beam"]
    q = gp.bondek(fl, members, profiles, f"{fr}-{lv}", tos, SLAB)
    kinds = [k for m in fl for k in m["end_kind"]]
    extra["floors"][f"{fr}-{lv}"] = {"ffl": ffl, "tos": tos, "beams": len(fl), **q, "bldgs": sorted({s["bldg"] for s in ss}),
                                     "free_ends": kinds.count("free"), "floating": sum(m["end_kind"] == ["free", "free"] for m in fl)}
    print(f"{fr}-{lv}: {len(fl)} beams, free ends {kinds.count('free')}, floating {extra['floors'][f'{fr}-{lv}']['floating']}, "
          f"open joints {len(opened)}, cautious {len(cautions)}, deck {q['deck_m2']:,} m2")

ids = {m["id"] for m in members}
for m in members:
    for k in (0, 1):                     # host dropped as too short -> square end
        if m["ends"][k] and m["ends"][k][0].get("host", m["id"]) not in ids:   # plane cuts have no host
            m["ends"][k] = None
            m["end_kind"][k] = "free"
json.dump({"profiles": profiles, "members": members}, open(sys.argv[2], "w", encoding="utf-8"), indent=0)
json.dump(extra, open(sys.argv[3], "w", encoding="utf-8"), indent=0)
print(f"{len(members)} members -> {sys.argv[2]}")
