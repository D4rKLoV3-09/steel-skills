#!/usr/bin/env python3
"""SJII (St. Joseph's Institution International): plan_members.json -> spec.json for geometry.py.

    python models/sjii/make_spec.py models/sjii/plan_members.json OUT_SPEC.json OUT_EXTRA.json

Source: Arup tender GA plans (T1, 30/10/26) for the Central Block (CTB 2101-2108), Education ES (2221-2229)
and HS (2321-2332), read by read_plans.py. FFL from the architectural sections; TOS = FFL - slab 150 (ASSUMED).
Frames: EDU (ES + HS) X from grid B1, Y from BA; CTB X from A1 + 200 m, Y from AA - 120 m (shown beside EDU, not in
site position). Z absolute mm.

Per floor: every marked beam line as drawn (curved beams as chords); each end
  - lands on a column outline (RC / steel) -> square end as drawn (RC by others, connection not detailed);
  - else meets another beam within 700 mm -> runs to that beam's axis, coped into an I host (welded, zero gap);
  - else free (wall bearing / cantilever, as drawn).
Steel columns: marks D40H / SC01 without a line -> column from the floor below to this floor's TOS.
Bondek package (ASSUMED Bondek II 1.0 BMT, studs 19x100 @300, edgeform 1.2 BMT x slab): deck strip between
neighbouring parallel beams <= 4.6 m apart; edgeform on the outline of the deck union; one stud row per beam.
EXTRA = ghosts (RC columns), per-floor deck m2 / edgeform m, counts for the report.

Rebuild (from the repo root; D = jobs/SJII/"Models Data"):
    python models/sjii/read_plans.py models/sjii/plan_members.json
    python models/sjii/make_spec.py models/sjii/plan_members.json $D/sjii.spec.json $D/sjii.extra.json
    python generate-model/geometry.py $D/sjii.spec.json $D/sjii.parts.json
    python models/sjii/make_data.py $D/sjii.spec.json $D/sjii.parts.json $D/sjii.extra.json $D/sjii.data.json
    python generate-model/tests/clash_check.py $D/sjii.data.json $D/sjii.spec.json
    python generate-model/build_model.py $D/sjii.data.json jobs/SJII/Models/SJII_Steel_Model.html
"""
import json
import math
import sys
from pathlib import Path

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sections import SCHED, lookup  # noqa: E402

SLAB = 150                 # "150 BDK" on the plans
CTB_DX, CTB_DY = 200000, -120000   # CTB drawn beside EDU (own grid frame, not site position)
COLMARK = {"D40H", "SC01"}
BLD = {"CTB": "Central Block", "ES": "Education ES", "HS": "Education HS"}

sheets = json.load(open(sys.argv[1], encoding="utf-8"))
profiles, members, extra = {}, [], {"ghosts": [], "floors": {}, "skipped": {}, "free_marks": {}}


def prof(mark):
    name = SCHED[mark]
    if name not in profiles:
        r = lookup(mark)
        p = {k: r[k] for k in ("type", "h", "b", "tw", "tf", "t", "kgm") if k in r}
        profiles[name] = p
        extra.setdefault("prof_info", {})[name] = r
    return name


def depth(name):
    p = profiles[name]
    return p.get("h", p.get("b"))


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
    beams, cols = [], []
    seen = set()
    for s in ss:
        bl = s["bldg"]
        for c in s["cols"]:
            cols.append({"c": [c["c"][0] + dx, c["c"][1] + dy], "s": c["s"], "fill": c["fill"]})
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
        for f in s["free"]:
            extra["free_marks"].setdefault(f["mark"], []).append(f"{bl}-{lv}")
    # RC column ghosts from the floor below (concrete by others)
    zb = below(fr, lv)
    z0 = round(zb * 1000 - SLAB) if zb else tos - 4500
    seenc = []
    for c in cols:
        if any(math.dist(c["c"], q) < 300 for q in seenc):
            continue
        seenc.append(c["c"])
        if c["fill"] or max(c["s"]) >= 450:
            extra["ghosts"].append({"n": "RC column (by others)", "c": [c["c"][0], c["c"][1], (z0 + tos) / 2],
                                    "s": [c["s"][0], c["s"][1], tos - z0]})
    # ---- beam ends ----
    for i, bm in enumerate(beams):
        bm["id"] = f"{fr}-{lv}-{i}"
        bm["prof"] = prof(bm["mark"])
        bm["d"] = depth(bm["prof"])
    arcs_join = {}
    for bm in beams:                       # chord joints of curved beams stay square, no snapping
        if bm["arc"]:
            for e in ("a", "b"):
                arcs_join.setdefault((round(bm[e][0]), round(bm[e][1])), []).append(bm["id"])

    for bm in beams:
        bm["a0"], bm["b0"] = list(bm["a"]), list(bm["b"])      # snapping reads the drawn lines only

    def axis(bm):
        a, b = bm["a0"], bm["b0"]
        L = math.dist(a, b)
        return a, ((b[0] - a[0]) / L, (b[1] - a[1]) / L), L

    for bm in beams:
        bm["ends"] = [None, None]
        bm["end_kind"] = ["free", "free"]
        a0, t, L = axis(bm)
        for k, e in enumerate(("a", "b")):
            E = bm[e + "0"]
            if bm["arc"] and len(arcs_join.get((round(E[0]), round(E[1])), [])) > 1:
                bm["end_kind"][k] = "arc"
                continue
            out = (-t[0], -t[1]) if k == 0 else t
            # column outline at the end
            hit = None
            for c in cols:
                r = max(c["s"]) / 2
                d = math.dist(E, c["c"])
                perp = abs((c["c"][0] - E[0]) * t[1] - (c["c"][1] - E[1]) * t[0])
                ahead = (c["c"][0] - E[0]) * out[0] + (c["c"][1] - E[1]) * out[1]
                if d < r + 600 and perp < max(r, 250) and ahead > -r and (hit is None or d < hit[0]):
                    hit = (d, c)
            if hit:
                bm["end_kind"][k] = "col"
                continue
            best = None
            for h in beams:
                if h is bm:
                    continue
                ha, ht, hL = axis(h)
                cr = t[0] * ht[1] - t[1] * ht[0]
                if abs(cr) < math.sin(math.radians(15)):
                    continue
                # intersection of bm axis with h axis
                wx, wy = ha[0] - a0[0], ha[1] - a0[1]
                s_ = (wx * ht[1] - wy * ht[0]) / cr          # along bm
                u_ = (wx * t[1] - wy * t[0]) / cr            # along h
                P = (a0[0] + s_ * t[0], a0[1] + s_ * t[1])
                move = math.dist(P, E)
                if move > 700 or not (-300 <= u_ <= hL + 300):
                    continue
                inner = 300 < u_ < hL - 300                  # h runs past the joint -> h is the host
                if not inner and (h["d"] < bm["d"] or (h["d"] == bm["d"] and h["id"] > bm["id"])):
                    continue                                 # corner: the deeper beam hosts
                if best is None or move < best[0]:
                    best = (move, h, P)
            if best:
                _, h, P = best
                bm[e] = [round(P[0], 1), round(P[1], 1)]
                ph = profiles[h["prof"]]
                face = "cope" if ph["type"] == "I" and profiles[bm["prof"]]["type"] == "I" else "near"
                bm["ends"][k] = [{"host": h["id"], "face": face}]
                bm["end_kind"][k] = "beam"
    # ---- curved beams: mitre the chord joints (bisector plane, zero gap / no overlap) ----
    byid = {bm["id"]: bm for bm in beams}
    for J, ids in arcs_join.items():
        if len(ids) != 2:
            continue
        A, B = byid[ids[0]], byid[ids[1]]
        t = []
        for bm in (A, B):                      # direction pointing away from the joint
            o = bm["b0"] if (round(bm["a0"][0]), round(bm["a0"][1])) == J else bm["a0"]
            L = math.dist(o, J)
            t.append(((o[0] - J[0]) / L, (o[1] - J[1]) / L))
        n = (t[0][0] - t[1][0], t[0][1] - t[1][1])
        nl = math.hypot(*n)
        if nl < 1e-6:
            continue
        n = (n[0] / nl, n[1] / nl)
        for bm in (A, B):
            k = 0 if (round(bm["a0"][0]), round(bm["a0"][1])) == J else 1
            bm["ends"][k] = [{"plane": [n[0], n[1], 0, n[0] * J[0] + n[1] * J[1]]}]
    # ---- write members ----
    for bm in beams:
        if math.dist(bm["a"], bm["b"]) < 100:
            extra["skipped"].setdefault("too short after snapping", []).append(bm["id"])
            continue
        zc = tos - bm["d"] / 2
        members.append({"id": bm["id"], "ref": bm["mark"], "prof": bm["prof"], "a": [*bm["a"], zc], "b": [*bm["b"], zc],
                        "up": [0, 0, 1], "rank": 2, "ends": bm["ends"], "layer": "beam", "floor": f"{fr}-{lv}",
                        "bldg": bm["bldg"], "src": f"{bm['sheet']} ({bm['mark']} {SCHED[bm['mark']]}); TOS {tos / 1000:+.3f} = FFL - {SLAB}",
                        "arc": bm["arc"], "end_kind": bm["end_kind"], "tos": tos})
    # ---- steel columns from free marks (D40H / SC01) ----
    for s in ss:
        for f in s["free"]:
            if f["mark"] not in COLMARK:
                continue
            at = [f["at"][0] + dx, f["at"][1] + dy]
            near = min(cols, key=lambda c: math.dist(c["c"], at), default=None)
            p = near["c"] if near and math.dist(near["c"], at) < 1500 else at
            if any(m["layer"] == "col" and math.dist(m["a"][:2], p) < 200 and m["floor"] == f"{fr}-{lv}" for m in members):
                continue
            pn = prof(f["mark"])
            members.append({"id": f"{fr}-{lv}-col{len(members)}", "ref": f["mark"], "prof": pn, "a": [p[0], p[1], z0],
                            "b": [p[0], p[1], tos - 0.0], "up": [1, 0, 0], "rank": 0, "ends": [None, None], "layer": "col",
                            "floor": f"{fr}-{lv}", "bldg": s["bldg"], "tos": tos,
                            "src": f"{s['sheet']} ({f['mark']} {SCHED[f['mark']]} at the mark); from the floor below "
                                   f"({z0 / 1000:+.3f}) to TOS {tos / 1000:+.3f} - ASSUMED storey"})
    # ---- bondek package ----
    fl = [m for m in members if m["floor"] == f"{fr}-{lv}" and m["layer"] == "beam"]
    strips = []
    for m in fl:
        a, b = m["a"][:2], m["b"][:2]
        L = math.dist(a, b)
        t = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        n = (-t[1], t[0])
        best = None
        for o in fl:
            if o is m:
                continue
            oa, ob = o["a"][:2], o["b"][:2]
            oL = math.dist(oa, ob)
            ot = ((ob[0] - oa[0]) / oL, (ob[1] - oa[1]) / oL)
            if abs(t[0] * ot[1] - t[1] * ot[0]) > 0.02:
                continue
            off = (oa[0] - a[0]) * n[0] + (oa[1] - a[1]) * n[1]
            if not (200 < off < 4600):
                continue
            s0 = sorted([(oa[0] - a[0]) * t[0] + (oa[1] - a[1]) * t[1], (ob[0] - a[0]) * t[0] + (ob[1] - a[1]) * t[1]])
            lo, hi = max(0, s0[0]), min(L, s0[1])
            if hi - lo < 0.5 * min(L, oL):
                continue
            if best is None or off < best[0]:
                best = (off, lo, hi)
        if best:
            off, lo, hi = best
            P = lambda s_, w: (a[0] + s_ * t[0] + w * n[0], a[1] + s_ * t[1] + w * n[1])
            strips.append({"poly": [P(lo, 0), P(hi, 0), P(hi, off), P(lo, off)], "c": P((lo + hi) / 2, off / 2),
                           "len": hi - lo, "wid": off, "t": t, "on": m["id"]})
    area = sum(s_["len"] * s_["wid"] for s_ in strips) / 1e6
    U = unary_union([Polygon(s_["poly"]).buffer(60, join_style=2) for s_ in strips]).buffer(-60, join_style=2) if strips else None
    rings = []
    if U is not None and not U.is_empty:
        geoms = getattr(U, "geoms", [U])
        for g in geoms:
            g = g.simplify(20)
            rings += [list(g.exterior.coords)] + [list(r.coords) for r in g.interiors]
    ef_len = 0
    for j, s_ in enumerate(strips):
        pn = f"BDK {round(s_['wid'])}"
        profiles.setdefault(pn, {"type": "PL", "b": round(s_["wid"], 1), "t": 1.0, "kgm": 0.0})
        c, t = s_["c"], s_["t"]
        members.append({"id": f"{fr}-{lv}-bdk{j}", "ref": None, "prof": pn,
                        "a": [c[0] - t[0] * s_["len"] / 2, c[1] - t[1] * s_["len"] / 2, tos + 0.5],
                        "b": [c[0] + t[0] * s_["len"] / 2, c[1] + t[1] * s_["len"] / 2, tos + 0.5], "up": [0, 0, 1], "rank": 9,
                        "ends": [None, None], "layer": "bdk", "floor": f"{fr}-{lv}", "bldg": None, "tos": tos,
                        "src": f"Deck between beam lines (BDK slab {SLAB} on the plans); Bondek II 1.0 BMT ASSUMED (0033 Type 1 1.0 BMT G550)",
                        "mto": {"kind": "measure", "uom": "m2", "cat": "Bondek", "desc": "Bondek II 1.0 BMT metal deck (ASSUMED)",
                                "len": round(s_["len"]), "wid": round(s_["wid"]), "assumed": ["desc"]}})
    for r in rings:
        for p, q in zip(r, r[1:]):
            L = math.dist(p, q)
            if L < 50:
                continue
            ef_len += L
            nrm = [(q[1] - p[1]) / L, -(q[0] - p[0]) / L, 0]
            members.append({"id": f"{fr}-{lv}-ef{len(members)}", "ref": None, "prof": f"EF 1.2x{SLAB}",
                            "a": [p[0], p[1], tos + SLAB / 2], "b": [q[0], q[1], tos + SLAB / 2], "up": nrm, "rank": 9,
                            "ends": [None, None], "layer": "ef", "floor": f"{fr}-{lv}", "bldg": None, "tos": tos,
                            "src": f"Slab edge / opening of the deck outline; edgeform ASSUMED 1.2 BMT x {SLAB}",
                            "mto": {"kind": "measure", "uom": "m", "cat": "Edgeform", "desc": f"Edgeform 1.2 BMT x {SLAB} high (ASSUMED)",
                                    "len": round(L), "assumed": ["desc"]}})
    profiles.setdefault(f"EF 1.2x{SLAB}", {"type": "PL", "b": SLAB, "t": 1.2, "kgm": 0.0})
    # one stud row per beam under the deck (shown as one 19 wide x 100 high strip on the top flange)
    profiles.setdefault("SS row 19x100", {"type": "PL", "b": 19, "t": 100, "kgm": 0.0})
    nst = 0
    under = U.buffer(300) if U is not None and not U.is_empty else None
    for m in fl:
        L = math.dist(m["a"][:2], m["b"][:2])
        n = int(L // 300)
        if n < 1 or under is None or LineString([m["a"][:2], m["b"][:2]]).intersection(under).length < 0.5 * L:
            continue                                  # studs only on beams under the deck
        nst += n
        members.append({"id": m["id"] + "-ss", "ref": None, "prof": "SS row 19x100",
                        "a": [m["a"][0], m["a"][1], tos + 50], "b": [m["b"][0], m["b"][1], tos + 50], "up": [0, 0, 1], "rank": 9,
                        "ends": [None, None], "layer": "ss", "floor": f"{fr}-{lv}", "bldg": m["bldg"], "host_beam": m["id"], "tos": tos,
                        "src": "Shear studs on beam under the bondek slab (ASSUMED 19x100 @300 single row; GN note 24)",
                        "mto": {"kind": "measure", "uom": "pcs", "cat": "Stud", "desc": "Shear stud 19 dia x 100 @300 (ASSUMED)",
                                "len": 100, "set": n, "assumed": ["desc"]}})
    extra["floors"][f"{fr}-{lv}"] = {"ffl": ffl, "tos": tos, "beams": len(fl), "deck_m2": round(area), "edgeform_m": round(ef_len / 1000),
                                     "studs": nst, "bldgs": sorted({s["bldg"] for s in ss})}
    print(f"{fr}-{lv}: {len(fl)} beams, deck {area:,.0f} m2, edgeform {ef_len / 1000:,.0f} m, studs {nst}")

ids = {m["id"] for m in members}
for m in members:
    m.pop("arc", None)
    for k in (0, 1):                     # host dropped as too short -> square end
        if m["ends"][k] and m["ends"][k][0].get("host", m["id"]) not in ids:   # plane cuts have no host
            m["ends"][k] = None
            m["end_kind"][k] = "free"
json.dump({"profiles": profiles, "members": members}, open(sys.argv[2], "w", encoding="utf-8"), indent=0)
json.dump(extra, open(sys.argv[3], "w", encoding="utf-8"), indent=0)
print(f"{len(members)} members -> {sys.argv[2]}")
