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
Trusses (truss_types.json from read_trusses.py; positions = the plan lines named "Truss <name>"): the elevation is
centred on its plan line, top chord at the floor TOS; top chord pieces join the floor's beams (so floor beams frame
into them and they run to their supports), bottom chord / verticals / diagonals follow the elevation and bear on
the chords. HS2 uses the HS1 elevation (Yang, 14/11/26); HS5 has no elevation and is left out.
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
TYPES = json.load(open(Path(__file__).resolve().parent / "truss_types.json", encoding="utf-8"))
TRUSS_TYPE = {**{k: k for k in TYPES}, "HS2": "HS1"}          # plan name -> elevation

sheets = json.load(open(sys.argv[1], encoding="utf-8"))
profiles, members, extra = {}, [], {"ghosts": [], "floors": {}, "skipped": {}, "free_marks": {}, "cautions": [], "open": [], "trusses": {}, "truss_left": []}


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
    # ---- trusses named on this floor: top chord pieces join the beams ----
    insts = []
    for s in ss:
        for t in s.get("trusses", []):
            if t["name"] not in TRUSS_TYPE:
                extra["truss_left"].append(f"{t['name']} ({s['sheet']}, {math.dist(t['a'], t['b']) / 1000:.1f} m)")
                continue
            a, b = [t["a"][0] + dx, t["a"][1] + dy], [t["b"][0] + dx, t["b"][1] + dy]
            if (b[0] < a[0]) if abs(b[0] - a[0]) > abs(b[1] - a[1]) else (b[1] < a[1]):
                a, b = b, a                              # elevation left = lower grid
            L = math.dist(a, b)
            d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            C = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            T = TYPES[TRUSS_TYPE[t["name"]]]
            inst = {"id": f"{fr}-{lv}-T{len(insts) + 1}", "name": t["name"], "T": T, "C": C, "d": d, "bldg": s["bldg"], "sheet": s["sheet"]}
            insts.append(inst)

            def on_line(bm):                             # a beam line drawn on the truss line is the truss itself
                return all(abs((p[0] - a[0]) * d[1] - (p[1] - a[1]) * d[0]) < 300 and -1000 < (p[0] - a[0]) * d[0] + (p[1] - a[1]) * d[1] < L + 1000
                           for p in (bm["a"], bm["b"]))
            dropped = [bm for bm in beams if on_line(bm)]
            if dropped:
                extra["trusses"].setdefault("replaced", []).append(f"{t['name']} {s['sheet']}: " + ", ".join(bm["mark"] for bm in dropped))
                beams[:] = [bm for bm in beams if not on_line(bm)]
            for c in T["tc"]:
                beams.append({"mark": c["mark"], "a": [round(C[0] + d[0] * c["x0"]), round(C[1] + d[1] * c["x0"])],
                              "b": [round(C[0] + d[0] * c["x1"]), round(C[1] + d[1] * c["x1"])], "arc": False, "bldg": s["bldg"],
                              "sheet": s["sheet"], "flat": c["flat"], "through": True, "truss": inst["id"], "tname": t["name"], "tx": [c["x0"], c["x1"]]})
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
                                  "on": o["mark"] if o else "column %d wide" % min(c["col"]["s"]),
                                  "fam": "TC" if bm.get("truss") else None, "on_fam": "TC" if o and o.get("truss") else None})
    extra["open"] += [f"{i} ({byid[i]['mark']})" for i in opened]
    for bm in beams:
        if math.dist(bm["a"], bm["b"]) < 100:
            extra["skipped"].setdefault("too short after joining", []).append(bm["id"])
            continue
        tr = bm.get("truss")
        Lb = math.dist(bm["a"], bm["b"])
        zc = tos - (profiles[bm["prof"]]["b"] if bm.get("flat") else depth(bm["prof"])) / 2      # flat = web horizontal
        members.append({"id": bm["id"], "ref": bm["mark"], "prof": bm["prof"], "a": [*bm["a"], zc], "b": [*bm["b"], zc],
                        "up": [(bm["a"][1] - bm["b"][1]) / Lb, (bm["b"][0] - bm["a"][0]) / Lb, 0] if bm.get("flat") else [0, 0, 1],
                        "rank": 1 if tr else 2, "ends": bm["ends"], "layer": "truss" if tr else "beam", "floor": f"{fr}-{lv}",
                        "bldg": bm["bldg"], "src": (f"Truss {bm['tname']} top chord: {bm['sheet']} (position), {TYPES[TRUSS_TYPE[bm['tname']]]['sheet']} "
                                                   f"({bm['mark']} {SCHED[bm['mark']]}); " if tr else f"{bm['sheet']} ({bm['mark']} {SCHED[bm['mark']]}); ")
                        + f"TOS {tos / 1000:+.3f} = FFL - {SLAB}", "end_kind": bm["end_kind"], "tos": tos,
                        **({"fam": "TC", "truss": tr, "tname": bm["tname"], "tx": bm["tx"]} if tr else {})})
    # ---- trusses: bottom chord, verticals, diagonals from the elevation, bearing on the chords ----
    for inst in insts:
        T, C, d = inst["T"], inst["C"], inst["d"]
        tcs = [m for m in members if m.get("truss") == inst["id"]]
        byid_m = {m["id"]: m for m in members}
        if not tcs:
            continue
        common = {"layer": "truss", "truss": inst["id"], "tname": inst["name"], "floor": f"{fr}-{lv}", "bldg": inst["bldg"], "tos": tos}
        P = lambda x: [round(C[0] + d[0] * x, 1), round(C[1] + d[1] * x, 1)]
        at = lambda pieces, x: min(pieces, key=lambda m: max(m["tx"][0] - x, x - m["tx"][1], 0))
        src = lambda what, mk: f"Truss {inst['name']} {what}: {T['sheet']} ({mk} {SCHED[mk]}), position {inst['sheet']}"
        bcs = []
        for j, c in enumerate(T["bc"]):
            bcs.append({**common, "id": f"{inst['id']}-BC{j + 1}", "ref": c["mark"], "prof": prof(c["mark"]), "fam": "BC", "rank": 1,
                        "a": [*P(c["x0"]), tos + c["z"]], "b": [*P(c["x1"]), tos + c["z"]], "up": [-d[1], d[0], 0] if c["flat"] else [0, 0, 1],
                        "ends": [None, None], "tx": [c["x0"], c["x1"]], "src": src("bottom chord", c["mark"])})
        members += bcs
        vert = {}
        for j, v in enumerate(T["v"]):
            t_, b_ = at(tcs, v["x"]), at(bcs, v["x"])
            vert[v["x"]] = f"{inst['id']}-V{j + 1}"
            members.append({**common, "id": vert[v["x"]], "ref": v["mark"], "prof": prof(v["mark"]), "fam": "W", "rank": 2,
                            "a": [*P(v["x"]), t_["a"][2]], "b": [*P(v["x"]), b_["a"][2]], "up": [d[0], d[1], 0],
                            "ends": [[{"host": t_["id"], "face": "near"}], [{"host": b_["id"], "face": "near"}]], "src": src("vertical", v["mark"])})
        for j, g in enumerate(T["d"]):
            t_, b_ = at(tcs, g["xt"]), at(bcs, g["xb"])
            ends = [[{"host": h["id"], "face": "near"}] + ([{"host": vert[x], "face": "near"}] if x in vert else []) for h, x in ((t_, g["xt"]), (b_, g["xb"]))]
            if g["xb"] in vert and not b_["tx"][0] + 600 < g["xb"] < b_["tx"][1] - 600:
                ends[1][0]["sep"] = True                 # at the very end of the bottom chord the diagonal bears on the vertical, not the chord
            for e, lim in ((0, g["xt"] <= t_["tx"][0] + 600), (1, g["xt"] >= t_["tx"][1] - 600)):
                if lim and t_["end_kind"][e] in ("beam", "col"):   # a diagonal at the end of the top chord stops where the chord stops
                    hm = byid_m.get(t_["ends"][e][0].get("host")) if t_["end_kind"][e] == "beam" else None
                    hp = profiles[hm["prof"]] if hm else None
                    off = (hp.get("b", hp.get("d", 0)) / 2 if hp else 0) * (1 if e == 0 else -1)
                    pe = t_["ab"[e]]
                    ends[0].append({"plane": [d[0], d[1], 0, d[0] * pe[0] + d[1] * pe[1] + off]})
            for o in T["d"]:                           # two diagonals at one node with no vertical between: mitred on the plane across the truss
                if o is g:
                    continue
                for k, e in enumerate(("xt", "xb")):
                    den = (g["xt"] - o["xt"]) - (g["xb"] - o["xb"])
                    lam = (g["xt"] - o["xt"]) / den if abs(den) > 1 else None        # where the two axes cross, 0 = top chord, 1 = bottom chord
                    cross = lam is not None and -0.1 < lam < 1.1 and (lam < 0.5) == (k == 0)
                    if g[e] not in vert and (cross or abs(g[e] - o[e]) < 400) and (g["xt"] + g["xb"]) != (o["xt"] + o["xb"]):
                        xm = g["xt"] + lam * (g["xb"] - g["xt"]) if cross else (g[e] + o[e]) / 2
                        pm = P(xm)
                        ends[k].append({"plane": [d[0], d[1], 0, d[0] * pm[0] + d[1] * pm[1]]})
            members.append({**common, "id": f"{inst['id']}-D{j + 1}", "ref": g["mark"], "prof": prof(g["mark"]), "fam": "W", "rank": 3,
                            "a": [*P(g["xt"]), t_["a"][2]], "b": [*P(g["xb"]), b_["a"][2]], "up": [0, 0, 1], "ends": ends, "src": src("diagonal", g["mark"])})
        extra["trusses"].setdefault("count", {}).setdefault(f"{inst['bldg']} {inst['name']}", []).append(inst["id"])
    for p, mark, s in steel_cols:
        members.append({"id": f"{fr}-{lv}-col{len(members)}", "ref": mark, "prof": prof(mark), "a": [p[0], p[1], z0],
                        "b": [p[0], p[1], tos - 0.0], "up": [1, 0, 0], "rank": 0, "ends": [None, None], "layer": "col",
                        "floor": f"{fr}-{lv}", "bldg": s["bldg"], "tos": tos,
                        "src": f"{s['sheet']} ({mark} {SCHED[mark]} at the mark); from the floor below "
                               f"({z0 / 1000:+.3f}) to TOS {tos / 1000:+.3f} - ASSUMED storey"})
    # ---- bondek package ----
    fl = [m for m in members if m["floor"] == f"{fr}-{lv}" and (m["layer"] == "beam" or m.get("fam") == "TC")]
    q = gp.bondek(fl, members, profiles, f"{fr}-{lv}", tos, SLAB)
    kinds = [k for m in fl for k in m["end_kind"]]
    extra["floors"][f"{fr}-{lv}"] = {"ffl": ffl, "tos": tos, "beams": len(fl), **q, "bldgs": sorted({s["bldg"] for s in ss}),
                                     "free_ends": kinds.count("free"), "floating": sum(m["end_kind"] == ["free", "free"] for m in fl)}
    print(f"{fr}-{lv}: {len(fl)} beams, free ends {kinds.count('free')}, floating {extra['floors'][f'{fr}-{lv}']['floating']}, "
          f"open joints {len(opened)}, cautious {len(cautions)}, deck {q['deck_m2']:,} m2")

ids = {m["id"] for m in members}
for m in members:
    m.pop("tx", None)
    for k in (0, 1):                     # a host dropped as too short: its cut goes, an end left with none is square
        cuts = m["ends"][k] or []
        keep = [c for c in cuts if c.get("host", m["id"]) in ids]
        if len(keep) != len(cuts):
            m["ends"][k] = keep or None
            if cuts[0] not in keep and "end_kind" in m:
                m["end_kind"][k] = "free"
json.dump({"profiles": profiles, "members": members}, open(sys.argv[2], "w", encoding="utf-8"), indent=0)
json.dump(extra, open(sys.argv[3], "w", encoding="utf-8"), indent=0)
print(f"{len(members)} members -> {sys.argv[2]}")
