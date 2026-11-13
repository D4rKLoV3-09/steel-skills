#!/usr/bin/env python3
"""SJII: spec.json + parts.json (geometry.py) + extra.json -> data.json for build_model.py.

    python models/sjii/make_data.py SPEC.json PARTS.json EXTRA.json OUT_DATA.json

Yang's tags (one-to-one per drawing mark, natural order): every beam mark (B.., BU09, C35KK, R20A) -> UB1..,
steel columns D40H / SC01 -> UC1.., bondek package BDK1 / SS1 / EF1.
Grouping: building (tower) > floor (MTO unit) > lift unit (every beam / column a single loose piece; deck +
edgeform per floor) > assembly (member; its stud row is a sub-assembly).
"""
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from read_plans import GX, GY  # noqa: E402

spec = json.load(open(sys.argv[1], encoding="utf-8"))
parts = json.load(open(sys.argv[2], encoding="utf-8"))
extra = json.load(open(sys.argv[3], encoding="utf-8"))
M = spec["members"]
assert len(M) == len(parts)
CTB_DX, CTB_DY = 200000, -120000
ES_HS_X = 54000                           # grid B7: ES west of it, HS from it (deck / edgeform split)

natural = lambda s: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]
mapping, count = {}, {}
for ref in sorted({m["ref"] for m in M if m["ref"]}, key=natural):
    f = "UC" if ref in ("D40H", "SC01") else "UB"
    count[f] = count.get(f, 0) + 1
    mapping[ref] = f"{f}{count[f]}"
TAG_FIX = {"bdk": "BDK1", "ss": "SS1", "ef": "EF1"}

# ---------------- units: building x floor ----------------
LVN = {"01": "1st Storey", "02": "2nd Storey", "03": "3rd Storey", "04": "4th Storey", "05": "5th Storey", "06": "6th Storey",
       "07": "7th Storey", "08": "8th Storey", "09": "9th Storey", "10": "10th Storey", "LR": "Lower Roof", "UR": "Upper Roof"}
BLD = {"CTB": "Central Block", "ES": "Education ES", "HS": "Education HS"}


def bldg_of(m, p):
    if m["bldg"]:
        return m["bldg"]
    if m["floor"].startswith("CTB"):
        return "CTB"
    x = sum(v[0] for f in p["pr"][0] for v in f) / sum(len(f) for f in p["pr"][0])
    return "ES" if x < ES_HS_X else "HS"


keys = []
for m, p in zip(M, parts):
    lv = m["floor"].split("-")[1]
    k = (bldg_of(m, p), lv)
    m["_u"] = k
    if k not in keys:
        keys.append(k)
order = {"CTB": 0, "ES": 1, "HS": 2}
lvo = list(LVN)
keys.sort(key=lambda k: (order[k[0]], lvo.index(k[1])))
ffl = {k: v["ffl"] for k, v in extra["floors"].items()}
UNITS = [(f"{b}-{lv}", f"{BLD[b]} {LVN[lv]} (FFL {ffl[('CTB' if b == 'CTB' else 'EDU') + '-' + lv]:+.3f})") for b, lv in keys]
UI = {k: i for i, k in enumerate(keys)}

# ---------------- grid text ----------------
EDU_X = sorted((v, k) for k, v in GX.items() if k.startswith("B"))
EDU_Y = sorted((v, k) for k, v in GY.items() if k.startswith("B"))
CTB_X = sorted((v + CTB_DX, k) for k, v in GX.items() if k.startswith("A") and len(k) > 1 and k[1:].isdigit())
CTB_Y = sorted((v + CTB_DY, k) for k, v in GY.items() if k.startswith("A") and not k[1:].isdigit())


def near(v, lines):
    p, k = min(lines, key=lambda g: abs(g[0] - v))
    d = v - p
    return k if abs(d) < 50 else f"{k} {d:+,.0f}"


def grid_txt(x, y, ctb):
    return f"{near(x, CTB_X if ctb else EDU_X)} / {near(y, CTB_Y if ctb else EDU_Y)}"


# ---------------- layers / categories ----------------
LAYERS = [("beam", "Floor beams (UB)", "#4f7cac"), ("col", "Steel columns (UC)", "#c9822b"), ("bdk", "Bondek deck", "#a7b3bf"),
          ("ss", "Shear studs (one row per beam)", "#d4a017"), ("ef", "Edgeform", "#5d7385"), ("ghost", "Ghost (RC columns, by others)", "#9aa3ad")]
LI = {k: i for i, (k, _, _) in enumerate(LAYERS)}
CATS = [("A", "FLOOR BEAMS (UB) - STEEL FABRICATED FRAMING", ["beam"], "GA plans CTB S-2101..2108, ES S-2221..2229, HS S-2321..2332 (T1)"),
        ("B", "STEEL COLUMNS (UC) - D40H CHS406.4 / SC01 SHS1200", ["col"], "ES / HS GA plans (marks at the column)"),
        ("C", "BONDEK PACKAGE - DECK (m2), SHEAR STUDS (pcs), EDGEFORM (m) - ASSUMED SPEC", ["bdk", "ss", "ef"],
         "GA plans '150 BDK'; S-0033 typical composite slab (1.0 BMT G550)")]

# ---------------- profiles ----------------
profs = {}
for name, r in extra["prof_info"].items():
    nums = re.findall(r"[\d.]+", name)
    cat = re.match(r"[A-Z]+", name).group(0)
    d, w, t = (nums + ["", "", ""])[:3] if cat != "CHS" else (nums[0], "", nums[1])
    profs[name] = {"d": d, "w": w, "t": t, "cat": cat, "kgm": r["kgm"], "m2m": r["m2m"], "src": r["src"]}
    if r["m2m_assumed"]:
        profs[name]["m2m_assumed"] = True
for name in {m["prof"] for m in M}:
    if name in profs:
        continue
    if name.startswith("BDK"):
        profs[name] = {"d": "", "w": "", "t": "1.0", "cat": "Bondek", "kgm": 0.0, "src": "Bondek deck - counted in m2 (bondek package)"}
    elif name.startswith("SS"):
        profs[name] = {"d": "19", "w": "100", "t": "", "cat": "Stud", "kgm": 0.0, "src": "Shear studs - counted in pcs (bondek package)"}
    else:
        profs[name] = {"d": "150", "w": "1.2", "t": "", "cat": "Edgeform", "kgm": 0.0, "src": "Edgeform - counted in m run (bondek package)"}

# ---------------- groups ----------------
groups, gidx = [], {}


def g(level, name, label=None):
    k = (level, name)
    if k not in gidx:
        gidx[k] = len(groups)
        groups.append({"level": level, "name": name, **({"label": label} if label else {})})
    return gidx[k]


by_id = {m["id"]: i for i, m in enumerate(M)}
out = []
for m, p in zip(M, parts):
    lay = m["layer"]
    b, lv = m["_u"]
    ctb = b == "CTB"
    q = {k: v for k, v in p.items() if k not in ("bldg", "floor", "layer", "end_kind", "tos", "host_beam", "_u", "rank", "ends", "up", "a", "b")}
    a, e = m["a"], m["b"]
    q.update({"t": TAG_FIX.get(lay) or mapping[m["ref"]], "layer": LI[lay], "unit": UI[m["_u"]],
              "tw": g("tower", BLD[b], "Building"), "sub": -1, "desc": m["prof"],
              "grid": grid_txt((a[0] + e[0]) / 2, (a[1] + e[1]) / 2, ctb) + f" @ {LVN[lv]}"})
    if m["ref"]:
        q["ref"] = m["ref"]
        q["desc"] = f"{m['prof']} ({m['ref']})"
    else:
        q.pop("ref", None)
    if lay in ("bdk", "ss", "ef"):
        q["grade"] = "TBC (proprietary, ASSUMED spec)"
        q["mto_desc"] = m["mto"]["desc"]
        q["desc"] = m["mto"]["desc"] + (f" - {m['mto']['set']} pcs" if lay == "ss" else "")
    out.append(q)
unit_name = dict(UNITS)
for m, q in zip(M, out):
    lay = m["layer"]
    uk = f"{m['_u'][0]}-{m['_u'][1]}"
    if lay == "ss":
        continue
    if lay in ("bdk", "ef"):
        q["lu"] = g("lift", f"Bondek deck + edgeform - {unit_name[uk]}")
        q["asm"] = g("asm", f"{q['t']} @ {q['grid']} ({m['id']})")
    else:
        q["lu"] = g("lift", f"{q['t']} @ {q['grid']} ({m['id']}, single loose piece)")
        q["asm"] = g("asm", f"{q['t']} @ {q['grid']} ({m['id']})")
for m, q in zip(M, out):
    if m["layer"] != "ss":
        continue
    host = out[by_id[m["host_beam"]]]
    q["lu"], q["asm"] = host["lu"], host["asm"]
    q["sub"] = g("sub", f"Shear studs SS1 on {host['t']} @ {host['grid']}")

# ---------------- notes ----------------
fl = extra["floors"]
kg_steel = sum(q["kg"] for q, m in zip(out, M) if m["layer"] in ("beam", "col"))
not_cons = sorted({n for n, r in extra["prof_info"].items() if r["kg_assumed"]})
fm = extra["free_marks"]
n_free_beam = sum(len(v) for k, v in fm.items() if k not in ("D40H", "SC01"))
n_beam = sum(1 for m in M if m["layer"] == "beam")
decisions = [
    "Trusses CTB1-CTB3 (S-8101) and ES1 / ES1a / HS1 (S-8201): NOT in this version (elevations have no plan level for CTB, "
    "two-storey trusses 4th-6th storey for EDU). A) model them in rev 2 from the elevations (estimate 250-400 t); "
    "B) take them from a Tekla / IFC model if the engineer has one; C) price them separately.",
    "Site position: CTB and EDU are shown side by side in their own grid frames (no common grid on the overall plan S-2001). "
    "A) keep (MTO unaffected); B) send the site setting-out so the blocks sit at their true angle.",
    f"Unpaired beam marks: {n_free_beam} marks ({n_free_beam / max(1, n_beam) * 100:.1f} % of {n_beam} modelled beams) could not be tied to a drawn line "
    "(dashed / below members, labels off the line). A) accept for tender with a 3 % allowance on beam tonnage; B) I trace them by hand in rev 2.",
    f"Sections not in the Consteel 2025 catalogue ({', '.join(not_cons)}): drawing designation weight used, red in the MTO. "
    "A) keep; B) confirm the mill (ArcelorMittal / ASTM jumbo) and the actual unit weight.",
]
assumptions = [
    "Levels: FFL from the architectural sections (CTB 1st 8.70 / 2nd 15.00 / 3rd 20.25 / 4th 28.10 / 5th 33.35 / 6th 38.60 / LR 43.85 / UR 49.10; "
    "EDU 1st 9.75 / 2nd 15.00 / 3rd 20.25 / 4th 25.50 / 5th 30.00 / 6th 34.50 / 7th 39.00 / 8th 43.50 / 9th 48.00 / 10th 52.50 / LR 57.00 / UR 63.50). "
    "CTB-specific section SJII-DPA-CTB-XX-A-2001 shows LR 38.60 / UR 43.85 (no 6th): the overall section and the structural set (6th storey plan S-2106) were followed.",
    f"Top of steel = FFL - {150} (150 BDK slab on the plans, no screed allowed) on every floor; all beams top-flange flush, web vertical.",
    "Plan positions read from the vector GA plans at 1:200 (70.56 mm/pt), calibrated on the grid bubbles (all bays 9,000; EDU BM-BN 4,500); "
    "ES and HS share grid B7 (duplicates on B7 removed).",
    "Beam ends: at an RC column / wall the beam stops where drawn (embed / cleat connection not detailed); secondary beams run to the axis of the "
    "beam they meet and are coped into it (welded, zero gap); free ends as drawn. Curved beams modelled as straight chords (about 12 per beam).",
    "Steel columns D40H (CHS406.4x14.2) and SC01 (SHS1200x1200x30, concrete filled - concrete by others) placed at their marks, from the floor below "
    "to the TOS of the floor they are marked on; CHS shown as an equal-area square box (weight from Consteel CHS).",
    "Unit weights and m2/m from Consteel 2025 (hollow sections hot-finished; RHS200x100x5 only cold-formed). UB/UC tw/tf in the 3D view derived from kg/m (display only). "
    "m2/m for hollow sections and sections not in Consteel computed from the outline - red.",
    "Grade S355JR for all structural steel (General Notes S-0001 note 6); bolts 8.8 (note 17) - no bolts modelled (connections not detailed).",
    "Bondek package (Yang's scope): Bondek II 1.0 BMT deck (S-0033 Type 1 1.0 BMT G550) between neighbouring parallel beams <= 4.6 m apart on every floor with a slab; "
    "shear studs 19x100 @300 single row on every beam under the deck (stud spacing S not given on S-0033); edgeform 1.2 BMT x 150 on the deck outline incl. openings - ASSUMED.",
    "Upper roofs (CTB UR, EDU UR): beams spaced over 4.6 m, no bondek / studs counted (roof type not on the structural set).",
    "CTB and EDU drawn beside each other in their own grid frames (CTB shifted +200 m / -120 m in the viewer); levels are true.",
]
left = [
    "Trusses CTB1, CTB2, CTB3 (S-8101) and ES1 / ES1a / HS1 (S-8201) - see Decisions (CTB4 plan S-2104 and ES / HS 4th storey plans show their lines).",
    f"{n_free_beam} beam marks not tied to a drawn line ({', '.join(f'{k} {len(v)}' for k, v in sorted(fm.items()) if k not in ('D40H', 'SC01'))}) - mostly dashed "
    "transfer members (BU09, C35KK) and marks placed off the line.",
    f"{len(extra['skipped'].get('too short after snapping', []))} drawn pieces shorter than 100 mm after joining to their supports.",
    "All connections (fin plates, end plates, cleats, embeds to RC, splices, stiffeners) and bolts - not detailed on the tender GA set.",
    "Basement B1 (S-2100) and 1st storey ES / HS (S-2221 / S-2321): no steel framing marked; EDU overall plans S-2201..2212 (key plans, no marks) not used.",
    "RC columns (ghost), core walls, RC slab topping, mesh, propping, fire protection (intumescent / board) - by others or not steel.",
    "No handrail, grating, chequered plate, staircase or cat ladder steel on the structural set (stairs are precast per note 5).",
]
cats = [{"code": c, "title": t, "layers": [LI[k] for k in ls], "dwg": dw} for c, t, ls, dw in CATS]
gx = [[k, v] for v, k in EDU_X] + [[k, v] for v, k in CTB_X]
gy = [[k, v] for v, k in EDU_Y] + [[k, v] for v, k in CTB_Y]
data = {
    "meta": {"title": "SJII Steel Framing", "grand_total_label": "SJII STEEL FRAMING", "currency": "RM", "export_prefix": "SJII",
             "card": {"title": "SJII - Central Block + Education Building (ES / HS) steel framing",
                      "desc": f"Steel floor framing on RC columns / cores, {n_beam:,} beams on {len(fl)} floors, bondek slabs",
                      "ref": "Arup tender GA set T1 (30/10/26) S-2101..2332 · S355JR"},
             "datum_z": 0, "grade": "S355JR", "unit_names": {k: v for k, v in UNITS}},
    "header": {"client": "ST. JOSEPH'S INSTITUTION INTERNATIONAL LTD", "project": "SJII - 1033 Upper Serangoon Road (Arup job 314457-00), tender",
               "description": "STRUCTURAL STEEL - FLOOR BEAMS, STEEL COLUMNS, BONDEK PACKAGE (from 3D model, version 1 - trusses not included)",
               "contractor": "", "date": "13-11-2026"},
    "parts": out, "groups": groups,
    "layers": [{"k": k, "n": n, "c": c} for k, n, c in LAYERS],
    "units": [n for _, n in UNITS], "unitKeys": [k for k, _ in UNITS],
    "ghosts": extra["ghosts"], "gx": gx, "gy": gy, "profs": profs, "cats": cats,
    "notes": assumptions, "left": left, "assumptions": assumptions, "decisions": decisions,
    "noteSections": [
        {"title": "Basis", "items": [
            "Arup tender drawings T1 (30/10/26): GA plans Central Block S-2101..2108, Education ES S-2221..2229, HS S-2321..2332; general notes S-0001 / 0002; composite slab S-0033.",
            "Member tags are Yang's (UB beams, UC columns, BDK / SS / EF); the drawing mark (B45Q, B61V, ...) is kept as Ref and is searchable.",
            "One MTO unit per building and storey; building = tower; every beam is its own lift unit (single loose piece)."]},
        {"title": "Decisions for Yang", "items": decisions},
        {"title": "Assumptions", "from": "assumptions"},
        {"title": "Left out of the model", "from": "left"}],
}
json.dump(data, open(sys.argv[4], "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(f"{len(out)} parts, steel {kg_steel:,.0f} kg, {len(groups)} groups, {len(UNITS)} units; tags: "
      + ", ".join(f"{k} {v}" for k, v in sorted(count.items())))
print("mapping:", ", ".join(f"{k}->{v}" for k, v in mapping.items()))
