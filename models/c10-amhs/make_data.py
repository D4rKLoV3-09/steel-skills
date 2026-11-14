#!/usr/bin/env python3
"""C10 SAC AMHS bridge: spec.json + parts.json (geometry.py) -> data.json for build_model.py.

    python make_data.py SPEC.json PARTS.json OUT_DATA.json

Yang's tags (one-to-one, natural order of the drawing marks per family): SC -> UC, TC / BC -> TC / BC,
VR + DG -> W, 1HSB / 1VSB / 2HSB / 2VSB -> UB, 1BR / 2BR -> BR, PR -> P; bondek package BDK / SS / EF.
Grouping: span (tower) > lift unit (north / south truss incl. its end columns; every floor, support-level,
bracing and purlin member a single loose piece; deck + edgeform per span) > assembly (member; studs are a
sub-assembly of the beam they are welded to). Studs that would land on a column, vertical or diagonal foot
are dropped (SAT clash with the other parts).
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "generate-model" / "tests"))
from clash_check import prisms, sat  # noqa: E402

import numpy as np  # noqa: E402

spec = json.load(open(sys.argv[1], encoding="utf-8"))
parts = json.load(open(sys.argv[2], encoding="utf-8"))
M = spec["members"]
assert len(M) == len(parts)

# ---------------- drop studs that clash ----------------
pr = prisms(parts)
lo = np.array([p[1].min(0) for p in pr]); hi = np.array([p[1].max(0) for p in pr])
is_ss = np.array([M[p[0]]["layer"] == "ss" for p in pr])
is_pkg = np.array([M[p[0]]["layer"] in ("ss", "bdk", "ef") for p in pr])   # studs go through the deck
drop = set()
others = np.where(~is_pkg)[0]
for k in np.where(is_ss)[0]:
    near = others[np.all(lo[others] < hi[k] - 0.5, axis=1) & np.all(hi[others] > lo[k] + 0.5, axis=1)]
    if any(sat(pr[k], pr[j]) > 0.5 for j in near):
        drop.add(pr[k][0])
keep = [i for i in range(len(M)) if i not in drop]
print(f"studs dropped (land on a column / vertical / diagonal foot): {len(drop)}")
M = [M[i] for i in keep]
parts = [parts[i] for i in keep]

# ---------------- Yang tags ----------------
natural = lambda s: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]


def family(ref):
    r = ref.replace("X-LB-", "")
    if r.startswith("SC"):
        return "UC"
    if r.startswith("TC"):
        return "TC"
    if r.startswith("BC"):
        return "BC"
    if r.startswith(("VR", "DG")):
        return "W"
    if re.match(r"\d(HSB|VSB)", r):
        return "UB"
    if re.match(r"\dBR", r):
        return "BR"
    if r.startswith("PR"):
        return "P"
    raise ValueError(ref)


mapping, count = {}, {}
for ref in sorted({m["ref"] for m in M if m["ref"]}, key=natural):
    f = family(ref)
    count[f] = count.get(f, 0) + 1
    mapping[ref] = f"{f}{count[f]}"
assert len(set(mapping.values())) == len(mapping)
TAG_FIX = {"bdk": "BDK1", "ss": "SS1", "ef": "EF1"}

# ---------------- layers / categories ----------------
LAYERS = [("col", "Support columns (SC)", "#4f7cac"), ("chord", "Truss chords (TC / BC)", "#c9822b"),
          ("web", "Truss verticals + diagonals", "#b04a5a"), ("l2", "Level 2 floor beams (1HSB / 1VSB)", "#7b68b5"),
          ("l3", "Level 3 support beams (2HSB / 2VSB)", "#8a6d3b"), ("br", "Plan bracing (1BR / 2BR)", "#2f9fb3"),
          ("pr", "Roof purlins", "#6b8e23"), ("bdk", "Bondek package (deck, studs, edgeform)", "#a7b3bf"),
          ("ghost", "Ghost (RC piers, by others)", "#9aa3ad")]
LI = {k: i for i, (k, _, _) in enumerate(LAYERS)}
LI["ss"] = LI["ef"] = LI["bdk"]          # Yang: bondek, studs and edgeform share one layer, hidden when the page opens
DWG = "XXXX-LAY-LA1-00-SSTEL-001 / XXXX-SEC-LA1-00-SSTEL-001 Rev D"
CATS = [("A", "TRUSS CHORDS - TOP / BOTTOM (TC / BC)", ["chord"], "LAY-001 plans 1-2; SEC-001 section 1-1"),
        ("B", "TRUSS VERTICALS AND DIAGONALS (VR / DG)", ["web"], "SEC-001 section 1-1"),
        ("C", "SUPPORT COLUMNS (SC)", ["col"], "LAY-001 plans 1-2; SEC-001 section 1-1"),
        ("D", "LEVEL 2 FLOOR BEAMS (1HSB / 1VSB) - TOS +21.850", ["l2"], "LAY-001 plan 1"),
        ("E", "LEVEL 3 SUPPORT BEAMS (2HSB / 2VSB) - TOS +30.109 / +30.320", ["l3"], "LAY-001 plan 2; SEC-001 1-1"),
        ("F", "PLAN BRACING (1BR / 2BR)", ["br"], "LAY-001 plans 1-2"),
        ("G", "ROOF PURLINS C250x75x20x3.0", ["pr"], "SEC-001 roof purlin plan"),
        ("H", "BONDEK PACKAGE - DECK (m2), SHEAR STUDS (pcs), EDGEFORM (m) - ASSUMED SPEC", ["bdk", "ss", "ef"],
         "LAY-001 plan 1 BONDEK SLAB 350 THK; SEC-001 typical section of bondek")]

UNITS = [("W", "West span LA1-LA2"), ("M", "Middle span LA2-LA3"), ("E", "East span LA3-LA4")]
UI = {k: i for i, (k, _) in enumerate(UNITS)}

# ---------------- profiles (Consteel 2025) ----------------
CON = {  # name: (d, w, t, cat, kgm, m2m, m2m_assumed, src)
    "UB 610x229x140": ("610", "229", "140", "UB", 139.9, 2.11, False, "Consteel 2025 UB/UC 139.9 (617.2x230.2); m2/m 2.11 Consteel"),
    "UB 610x305x238": ("610", "305", "238", "UB", 238.1, 2.45, False, "Consteel 2025 UB/UC 238.1 (635.8x311.4); m2/m 2.45 Consteel"),
    "UB 914x419x343": ("914", "419", "343", "UB", 343.3, 3.42, False, "Consteel 2025 UB/UC 343.3 (911.8x418.5); m2/m 3.42 Consteel"),
    "UB 610x305x179": ("610", "305", "179", "UB", 179.0, 2.41, False, "Consteel 2025 UB/UC 179 (620.2x307.1); m2/m 2.41 Consteel"),
    "UB 610x305x149": ("610", "305", "149", "UB", 149.1, 2.39, False, "Consteel 2025 UB/UC 149.1 (612.4x304.8); m2/m 2.39 Consteel"),
    "UB 406x140x46": ("406", "140", "46", "UB", 46.0, 1.34, False, "Consteel 2025 UB/UC 46 (403.2x142.2); m2/m 1.34 Consteel"),
    "UB 914x305x253": ("914", "305", "253", "UB", 253.4, 2.99, False, "Consteel 2025 UB/UC 253.4 (918.4x305.5); m2/m 2.99 Consteel"),
    "UC 254x254x167": ("254", "254", "167", "UC", 167.1, 1.58, False, "Consteel 2025 UB/UC 167.1 (289.1x265.2); m2/m 1.58 Consteel"),
    "UC 305x305x283": ("305", "305", "283", "UC", 282.9, 1.94, False, "Consteel 2025 UB/UC 282.9 (365.3x322.2); m2/m 1.94 Consteel"),
    "UC 305x305x158": ("305", "305", "158", "UC", 158.1, 1.84, False, "Consteel 2025 UB/UC 158.1 (327.1x311.2); m2/m 1.84 Consteel"),
    "UC 152x152x23": ("152", "152", "23", "UC", 23.0, 0.889, False, "Consteel 2025 UB/UC 23 (152.4x152.2); m2/m 0.889 Consteel"),
    "BU 850x400x25x16": ("850", "400", "25/16", "BU", 257.48, 3.27, True,
                         "Built-up per legend detail: 2 x PL400x25 + PL800x16, 257.48 kg/m computed at 7.85 (not in Consteel); m2/m 3.27 computed from outline - ASSUMED"),
    "SHS100x100x6.3": ("100", "100", "6.3", "SHS", 18.4, 0.39, True, "Consteel 2025 SHS hot finished EN10210 100x100 t6.3 18.4 (hot-finished assumed); m2/m 0.39 computed from outline - ASSUMED"),
    "SHS180x180x6.3": ("180", "180", "6.3", "SHS", 34.2, 0.71, True, "Consteel 2025 SHS hot finished EN10210 180x180 t6.3 34.2 (hot-finished assumed); m2/m 0.71 computed from outline - ASSUMED"),
    "C250x75x20x3.0": ("250", "75", "3", "C", 9.89, 0.88, True, "Consteel 2025 lipped channel JIS G3350 250x75x20 t3 9.89 (= drawing 9.89 kg/m); m2/m 0.88 computed from outline - ASSUMED"),
    "SS 19x100": ("19", "100", "", "Stud", 0.0, None, False, "Shear stud - counted in pcs (bondek package)"),
    "EF 1.2x350": ("350", "1.2", "", "Edgeform", 0.0, None, False, "Edgeform - counted in m run (bondek package)"),
}
profs = {}
for name in sorted({m["prof"] for m in M}):
    if name.startswith("BDK"):
        profs[name] = {"d": "", "w": "", "t": "1.0", "cat": "Bondek", "kgm": 0.0, "src": "Bondek deck - counted in m2 (bondek package)"}
        continue
    d, w, t, cat, kgm, m2m, ass, src = CON[name]
    profs[name] = {"d": d, "w": w, "t": t, "cat": cat, "kgm": kgm, "src": src}
    if m2m is not None:
        profs[name]["m2m"] = m2m
    if ass:
        profs[name]["m2m_assumed"] = True

DESC = {"BU 850x400x25x16": "Built-up I 850x400 (PL400x25 flanges, PL800x16 web)"}

# ---------------- groups ----------------
groups, gidx = [], {}


def g(level, name, label=None):
    k = (level, name)
    if k not in gidx:
        gidx[k] = len(groups)
        groups.append({"level": level, "name": name, **({"label": label} if label else {})})
    return gidx[k]


SPAN_NAME = dict(UNITS)
by_id = {m["id"]: i for i, m in enumerate(M)}
out = []
for m, p in zip(M, parts):
    lay = m["layer"]
    tag = TAG_FIX.get(lay) or mapping[m["ref"]]
    sp = m["span"]
    tw = g("tower", SPAN_NAME[sp], "Span")
    q = {k: v for k, v in p.items() if k not in ("span", "lu", "side", "host_beam", "layer")}
    q.update({"t": tag, "layer": LI[lay], "unit": UI[sp], "tw": tw, "sub": -1, "desc": DESC.get(m["prof"], m["prof"])})
    if m["ref"]:
        q["ref"] = m["ref"]
    else:
        q.pop("ref", None)
    if lay in ("bdk", "ss", "ef"):
        q["grade"] = "TBC (proprietary, ASSUMED spec)"
        q["mto_desc"] = m["mto"]["desc"]
    out.append(q)
# assemblies and lift units
for i, (m, q) in enumerate(zip(M, out)):
    lay, sp = m["layer"], m["span"]
    if lay == "ss":
        continue
    if lay in ("bdk", "ef"):
        q["lu"] = g("lift", f"Bondek deck + edgeform - {SPAN_NAME[sp]}")
    elif m.get("lu"):
        q["lu"] = g("lift", m["lu"].replace(" - W", " - West span").replace(" - M", " - Middle span").replace(" - E", " - East span"))
    else:
        q["lu"] = g("lift", f"{q['t']} @ {m['grid']} (single loose piece)")
    q["asm"] = g("asm", f"{q['t']} @ {m['grid']}" + (f" ({m['id']})" if lay in ("bdk", "ef") else ""))
for m, q in zip(M, out):
    if m["layer"] != "ss":
        continue
    host = out[by_id[m["host_beam"]]]
    q["lu"], q["asm"] = host["lu"], host["asm"]
    q["sub"] = g("sub", f"Shear studs SS1 on {host['t']} @ {M[by_id[m['host_beam']]]['grid']}")

# ---------------- notes ----------------
assumptions = [
    "Levels: level 2 steel (bottom chords, 1HSB, 1VSB) top TOS +21.850 (plan 1); bondek slab 350 THK to FFL 22.200; built-up BC-02 bottom = BOB +21.000 (section 1-1).",
    "Level 3: truss top chords and 2HSB cross beams top +30.320 (scaled from section 1-1, TC-02 850 deep -> bottom +29.470); 2VSB @1200 top TOS +30.109 (TYP., plan 2); 2VSB09 UB914 cantilevers top +30.320, bottom = BOB +29.402.",
    "Support columns SC01-SC04 from +20.800 (base over TOC +20.732 + grout) to the chord top +30.320; section depth along Y as drawn on the plans.",
    "West span LA1-LA2 is skewed as drawn: trusses from (710, 13,800 / 4,200) at LA1 to (17,650, 9,685 / 85) at LA2 (13.65 deg); its 1VSB rows 2,400 and 2VSB rows 1,200 square to the chords.",
    "South truss (grid LAB) is not sectioned on this set (sections 2-4 are on SEC-002, not received): modelled as the mirror of section 1-1, diagonals tagged DG11-DG17 from the legend.",
    "1BR plan bracing SHS100x100x6.3 per legend (general note says 100x100x6.0 SHS): top +21.825 under the chord / beam top flanges, ends on the chord and beam webs.",
    "2BR plan bracing SHS180x180x6.3: top +29.700 under the level-3 beams, ends on the TC-02 web (middle span) or under TC-01 / TC-03; X-brace = one continuous diagonal NW-SE + two halves (marks per half as drawn).",
    "Roof purlins C250x75x20x3.0 @1200 (rows 7 x 1,200 + 475 + 725 from LAA): underside +30.608 (section 1-1), one simple span per bay between 2HSB lines; no purlins over the LA2 / LA3 span joints.",
    "Built-up chord TC-02 / BC-02 850x400 (PL400x25 flanges, PL800x16 web): 257.48 kg/m computed (not in Consteel).",
    "m2/m for SHS, C250 purlins and the built-up chord computed from the outline (not in Consteel) - red in the MTO.",
    "Bondek package (Yang's scope, not specified on the drawings): Bondek II 1.0 BMT deck over the whole level-2 slab, shear studs 19x100 @300 single row on every beam under the slab (1HSB, 1VSB, BC chords; studs at column / vertical / diagonal feet dropped), edgeform 1.2 BMT x 350 at every slab edge - ASSUMED.",
    "Beam-to-beam joints welded / coped as drawn lines meet (zero gap); 2VSB bottom flange cope at the 2HSB bottom flange (bottoms within 2 mm on the drawing) not modelled - shows as a 7-10 mm overlap.",
    "Grade S275 for all steel (general note); bondek, studs and edgeform TBC.",
]
left = [
    "22 unmarked transverse members at the third points of every level-3 bay (plan 2, heavy lines @1,700 / 1,882 / 2,192) - no mark, no size, not on section 1-1.",
    "Purlin seats between the 2HSB top (+30.320) and the purlin underside (+30.608), one per purlin per 2HSB line - drawn on section 1-1, not sized.",
    "Sag rods (roof plan, SAG ROD TYPICAL, 2 lines per bay = 3 equal spaces, about 200 pieces x 1.2 m) - size not given.",
    "X-LB-2VSB10 / 2VSB11 (UB914x305x253) and X-LB-2BR / DG marks are in the legend but 2VSB10 / 2VSB11 are on no plan (SEC-002 not received).",
    "Connection plates, gussets, stiffeners, base plates and bolts - not detailed on the tender set.",
    "RC piers (ghost), concrete topping, insulation, roof sheeting and the AMHS track - by others / not steel.",
    "Intumescent fire protection (general note) - by others; painting m2 given in the MTO.",
    "No handrail or grating on the drawings.",
]
decisions = [
    "Level-3 third-point members (22 no., unmarked heavy lines on plan 2): A) leave out (current); B) model as UB406x140x46 like the 2VSB (about 9.6 t); C) send the mark / size.",
    "Purlin seats +30.320 -> +30.608 at every 2HSB (about 280 no.): A) leave out (current); B) 288 high C250 stub cleat per purlin (about 0.8 t); C) send the detail.",
    "Sag rods: A) leave out (current); B) M12 rod with nuts, about 200 x 1.2 m (about 0.2 t).",
]
cats = [{"code": c, "title": t, "layers": [LI[k] for k in ls], "dwg": dw} for c, t, ls, dw in CATS]
ghosts = []
for m in M:
    if m["layer"] == "col":
        ghosts.append({"n": "RC pier (by others)", "c": [m["a"][0], m["a"][1], 20732 - 1000], "s": [700, 1100, 2000]})
data = {
    "meta": {"title": "C10 SAC AMHS Bridge", "grand_total_label": "AMHS BRIDGE", "currency": "RM", "export_prefix": "C10_SAC_AMHS",
             "card": {"title": "C10 SAC - AMHS Bridge (LA1-LA4)", "desc": "Two-level steel truss bridge, 3 spans on RC piers, bondek floor at FFL 22.200",
                      "ref": f"{DWG} · all steel S275"},
             "datum_z": 20732, "grade": "S275", "unit_names": {k: v for k, v in UNITS}},
    "header": {"client": "EXYTE SINGAPORE PTE LTD", "project": "C10 SAC - AMHS Bridge (LA1-LA4), job SG.01084",
               "description": "STRUCTURAL STEEL - TRUSSES, SUPPORT COLUMNS, FLOOR + SUPPORT-LEVEL BEAMS, BRACING, ROOF PURLINS, BONDEK PACKAGE (from 3D model)",
               "contractor": "", "date": "12-11-2026"},
    "parts": out, "groups": groups,
    "layers": [dict({"k": k, "n": n, "c": c}, **({"off": True} if k == "bdk" else {})) for k, n, c in LAYERS],
    "units": [n for _, n in UNITS], "unitKeys": [k for k, _ in UNITS],
    "ghosts": ghosts, "gx": [["LA1", 0], ["LA2", 18000], ["LA3", 49200], ["LA4", 62700]], "gy": [["LAB", 0], ["LAA", 9600]],
    "profs": profs, "cats": cats,
    "notes": assumptions, "left": left, "assumptions": assumptions, "decisions": decisions,
    "noteSections": [
        {"title": "Basis", "items": [
            f"Exyte tender drawings {DWG} (03 Nov 2026 tender addendum): framing plans TOS +21.850 and support level, roof purlin plan, section 1-1, legend.",
            "Member tags are Yang's (UC, TC / BC, W, UB, BR, P, BDK / SS / EF); the drawing mark is kept as Ref and is searchable.",
            "Concentric work points: chords on column webs, verticals and diagonals chord centroid to chord centroid cut to the bearing faces; cross beams coped into the chords (welded, zero gap)."]},
        {"title": "Decisions for Yang", "items": decisions},
        {"title": "Assumptions", "from": "assumptions"},
        {"title": "Left out of the model", "from": "left"}],
}
json.dump(data, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
kg = sum(q["kg"] for q, m in zip(out, M) if m["layer"] not in ("bdk", "ss", "ef"))
print(f"{len(out)} parts, steel {kg:,.0f} kg, {len(groups)} groups; tags: " + ", ".join(f"{k} {v}" for k, v in sorted(count.items())))
