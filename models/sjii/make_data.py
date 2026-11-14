#!/usr/bin/env python3
"""SJII: spec.json + parts.json (geometry.py) + extra.json -> data.json for build_model.py.

    python models/sjii/make_data.py SPEC.json PARTS.json EXTRA.json OUT_DATA.json

Yang's tags (one-to-one per drawing mark, natural order): every beam mark (B.., BU09, C35KK, R20A) -> UB1..,
steel columns D40H / SC01 -> UC1.., truss top chord / bottom chord / web marks -> TC1.. / BC1.. / W1..,
bondek package BDK1 / SS1 / EF1. Every truss is one lift unit ("Truss CTB1 @ grid").
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
FAM = lambda m: m.get("fam") or ("UC" if m["ref"] in ("D40H", "SC01") else "UB")       # truss members: TC / BC / W
tags, count = {}, {}
for f, ref in sorted({(FAM(m), m["ref"]) for m in M if m["ref"]}, key=lambda k: (k[0], natural(k[1]))):
    count[f] = count.get(f, 0) + 1
    tags[(f, ref)] = f"{f}{count[f]}"
mapping = {ref: t for (f, ref), t in tags.items() if f in ("UB", "UC")}
tag_of = lambda ref, fam=None: tags.get((fam, ref)) or mapping.get(ref)
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
LAYERS = [("beam", "Floor beams (UB)", "#4f7cac"), ("truss", "Trusses (TC / BC / W)", "#b5543f"), ("col", "Steel columns (UC)", "#c9822b"), ("bdk", "Bondek package (deck, studs, edgeform)", "#a7b3bf"),
          ("ghost", "Ghost (RC columns, by others)", "#9aa3ad")]
LI = {k: i for i, (k, _, _) in enumerate(LAYERS)}
LI["ss"] = LI["ef"] = LI["bdk"]          # Yang: bondek, studs and edgeform share one layer, hidden when the page opens
CATS = [("A", "FLOOR BEAMS (UB) - STEEL FABRICATED FRAMING", ["beam"], "GA plans CTB S-2101..2108, ES S-2221..2229, HS S-2321..2332 (T1)"),
        ("B", "TRUSSES (TC / BC / W) - CTB1-3, ES1, ES1a, HS1, HS2", ["truss"], "S-8101, S-8201 elevations; positions S-2104, S-2224, S-2324, S-2326"),
        ("C", "STEEL COLUMNS (UC) - D40H CHS406.4 / SC01 SHS1200", ["col"], "ES / HS GA plans (marks at the column)"),
        ("D", "BONDEK PACKAGE - DECK (m2), SHEAR STUDS (pcs), EDGEFORM (m) - ASSUMED SPEC", ["bdk", "ss", "ef"],
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
DEPTH = lambda n: spec["profiles"][n].get("h", spec["profiles"][n].get("d", spec["profiles"][n].get("b")))
WORD = {"deep": "frames into the shallower", "butt": "butts in line with", "wide": "is wider than its"}
caution_of = {}
for c in extra["cautions"]:
    other = f"{tag_of(c['on'], c.get('on_fam'))} (Ref {c['on']})" if tag_of(c["on"], c.get("on_fam")) else c["on"]
    caution_of.setdefault(c["id"], []).append(f"{WORD[c['k']]} {other}")
out = []
for m, p in zip(M, parts):
    lay = m["layer"]
    b, lv = m["_u"]
    ctb = b == "CTB"
    q = {k: v for k, v in p.items() if k not in ("bldg", "floor", "layer", "end_kind", "tos", "host_beam", "_u", "rank", "ends", "up", "a", "b", "fam", "truss", "tname", "flat")}
    a, e = m["a"], m["b"]
    q.update({"t": TAG_FIX.get(lay) or tags[(FAM(m), m["ref"])], "layer": LI[lay], "unit": UI[m["_u"]],
              "tw": g("tower", BLD[b], "Building"), "sub": -1, "desc": m["prof"],
              "grid": grid_txt((a[0] + e[0]) / 2, (a[1] + e[1]) / 2, ctb) + f" @ {LVN[lv]}"})
    if m["id"] in caution_of:
        q["src"] = "CAUTIOUS: " + "; ".join(caution_of[m["id"]]) + " | " + q.get("src", "")
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
truss_lu = {}
for m, q in zip(M, out):
    if m.get("fam") == "TC" and m["truss"] not in truss_lu:
        truss_lu[m["truss"]] = f"Truss {m['tname']} @ {q['grid']} ({m['truss']})"
for m, q in zip(M, out):
    lay = m["layer"]
    uk = f"{m['_u'][0]}-{m['_u'][1]}"
    if lay == "ss":
        continue
    if lay == "truss":
        q["desc"] += {"TC": " top chord", "BC": " bottom chord", "W": " web"}[m["fam"]] + f" of Truss {m['tname']}"
        q["lu"] = g("lift", truss_lu[m["truss"]], "Truss")
        q["asm"] = g("asm", f"{q['t']} @ {q['grid']} ({m['id']})")
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
from sections import SCHED  # noqa: E402
grp = {}
for c in extra["cautions"]:
    a_, b_ = (c["mark"], c.get("fam")), (c["on"], c.get("on_fam"))
    if c["k"] == "butt" and str(b_) < str(a_):          # a butt joint is seen from both members: one line per pair, not two
        a_, b_ = b_, a_
    grp.setdefault((c["bldg"], c["k"], a_, b_), []).append(c)
njoint = lambda k, cs: len(cs) if k != "butt" else max(len({c["id"] for c in cs if (c["mark"], c.get("fam")) == mk}) for mk in {(c["mark"], c.get("fam")) for c in cs})
sec = lambda r: f"{tag_of(*r)} (Ref {r[0]}, {SCHED[r[0]]})" if tag_of(*r) else r[0]
TXT = {"deep": "{a} frames into the shallower {b}", "butt": "{a} butts in line with {b} - different sections",
       "wide": "{a} is wider than its {b}"}
cautions = []
for (b, k, mk, on), cs in sorted(grp.items(), key=lambda kv: (-len(kv[1]), str(kv[0]))):
    lvs = sorted({c["floor"].split("-")[1] for c in cs}, key=list(LVN).index)
    dwg = sorted({re.search(r"S-\d{4}", c["sheet"]).group(0) for c in cs})
    cautions.append(f"{BLD[b]}: " + TXT[k].format(a=sec(mk), b=sec(on)) + f" - {njoint(k, cs)} joint{'s' if njoint(k, cs) > 1 else ''} "
                    f"on {', '.join(LVN[v] for v in lvs)} ({', '.join(dwg)})")
CAUT_MAX = 30
cautions_mto = cautions[:CAUT_MAX] + ([f"+ {len(cautions) - CAUT_MAX} more pairs ({sum(len(v) for v in grp.values()) - sum(len(v) for v in sorted(grp.values(), key=len, reverse=True)[:CAUT_MAX])} joints) - full list in the model Notes; every such member reads CAUTIOUS in its source line"] if len(cautions) > CAUT_MAX else [])
n_ends = 2 * sum(1 for m in M if m["layer"] == "beam")
tcount = {k: len(v) for k, v in extra["trusses"].get("count", {}).items()}
tkg = {}
for m, q in zip(M, out):
    if m["layer"] == "truss":
        tkg[m["tname"]] = tkg.get(m["tname"], 0) + q["kg"]
truss_t = sum(tkg.values()) / 1000
hs_tc = sum(q["L"] for m, q in zip(M, out) if m.get("fam") == "TC" and m["ref"] == "B61T") / 1000 * (393.0 - 179.0) / 1000
n_free = sum(v["free_ends"] for v in extra["floors"].values())
n_float = sum(v["floating"] for v in extra["floors"].values())
n_line = sum(k == "line" for m in M if m["layer"] == "beam" for k in m["end_kind"])
fl = extra["floors"]
kg_steel = sum(q["kg"] for q, m in zip(out, M) if m["layer"] in ("beam", "col"))
not_cons = sorted({n for n, r in extra["prof_info"].items() if r["kg_assumed"]})
fm = extra["free_marks"]
n_free_beam = sum(len(v) for k, v in fm.items() if k not in ("D40H", "SC01"))
n_beam = sum(1 for m in M if m["layer"] == "beam")
decisions = [
    f"Truss HS1 top chord: S-8201 labels it B61T | C35W | B61T but draws it 419 deep, the size of C35W. The labels were followed (UB610x305x179). "
    f"A) keep; B) C35W full length: + {hs_tc:.0f} t on the {tcount.get('HS HS1', 0) + tcount.get('HS HS2', 0)} HS trusses.",
    f"HS 6th storey: Truss HS2 x {tcount.get('HS HS2', 0)} has no elevation on the set; modelled with the HS1 elevation as you confirmed (14/11/26) = {tkg.get('HS2', 0) / 1000:.0f} t. "
    f"Truss HS5 ({', '.join(extra['truss_left']) or 'S-2326'}; the plan names it twice) and the truss-symbol lines without a name on the HS 4th storey edges have no elevation: not in. "
    "A) ask Arup for the HS2 / HS5 elevations; B) allow tonnage for HS5 by length.",
    "Truss CTB3: the five plan lines carry both the beam mark B61V and the name Truss CTB3; modelled as the truss only (top chord C35FF). "
    "A) keep; B) add the B61V beams on top (5 x 7.2 m = 5.6 t).",
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
    "Beam ends: the plans draw every beam line short of its support, so every end is run on to its neighbour within 1.5 m - the face of a column "
    "(RC or steel), the axis of the beam it meets (coped into it, zero gap; where several meet the deepest runs through), or the beam in line with it "
    "(butt joint at mid-gap). Lengths in this MTO are therefore support to support, not the drawn line lengths.",
    f"{n_line} beam ends ({n_line / n_ends * 100:.1f} %) stop on a drawn line without a mark (RC wall edge or unmarked member); {n_free} ends ({n_free / n_ends * 100:.1f} %) "
    f"found no neighbour within 1.5 m and stay as drawn (cantilever tip or a support not on the steel plans); {n_float} beams have no support found at either end; "
    f"{len(extra['open'])} joints where the supporting beam is drawn stopping short. Curved beams modelled as straight chords (about 12 per beam).",
    f"Trusses ({sum(tcount.values())} no., {truss_t:,.0f} t: " + ", ".join(f"{k.split()[1]} x {v}" for k, v in sorted(tcount.items())) + "): members from the elevations S-8101 / S-8201 (1:50, outlines), "
    "each truss placed on the plan line that names it, elevation centred on that line, top chord at the floor top of steel; top chords run to their supports like the floor beams; "
    "verticals and diagonals bear on the chords (welded, zero gap). Chords of CTB1 / CTB2 lie flat (web horizontal) as drawn. "
    "CTB2 chords carry no mark on S-8101: taken as BU09 (drawn 421 wide). HS1 bottom chord carries no mark: taken as C35W (drawn 419 deep).",
    "Steel columns D40H (CHS406.4x14.2) and SC01 (SHS1200x1200x30, concrete filled - concrete by others) placed at their marks, from the floor below "
    "to the TOS of the floor they are marked on. RC columns shown round or rectangular as drawn (ghost, by others).",
    "Unit weights and m2/m from Consteel 2025 (hollow sections hot-finished; RHS200x100x5 only cold-formed). UB/UC tw/tf in the 3D view derived from kg/m (display only). "
    "m2/m for hollow sections and sections not in Consteel computed from the outline - red.",
    "Grade S355JR for all structural steel (General Notes S-0001 note 6); bolts 8.8 (note 17) - no bolts modelled (connections not detailed).",
    "Bondek package (Yang's scope): Bondek II 1.0 BMT deck (S-0033 Type 1 1.0 BMT G550) between neighbouring parallel beams <= 4.6 m apart on every floor with a slab; "
    "shear studs 19x100 @300 single row on every beam under the deck (stud spacing S not given on S-0033); edgeform 1.2 BMT x 150 on the deck outline incl. openings - ASSUMED.",
    "Upper roofs (CTB UR, EDU UR): beams spaced over 4.6 m, no bondek / studs counted (roof type not on the structural set).",
    "CTB and EDU drawn beside each other in their own grid frames (CTB shifted +200 m / -120 m in the viewer); levels are true.",
]
left = [
    "Truss HS5 (HS 6th storey, S-2326) and the unnamed truss-symbol lines on the HS 4th storey (S-2324): no elevation on the set - see Decisions.",
    "Truss gussets, splices, bearing / end plates and the chord end details at the RC columns: not detailed on S-8101 / S-8201.",
    f"{n_free_beam} beam marks not tied to a drawn line ({', '.join(f'{k} {len(v)}' for k, v in sorted(fm.items()) if k not in ('D40H', 'SC01'))}) - mostly dashed "
    "transfer members (BU09, C35KK) and marks placed off the line.",
    f"{len(extra['skipped'].get('too short after joining', []))} drawn pieces shorter than 100 mm after joining to their supports.",
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
                      "desc": f"Steel floor framing on RC columns / cores, {n_beam:,} beams on {len(fl)} floors, {sum(tcount.values())} trusses, bondek slabs",
                      "ref": "Arup tender GA set T1 (30/10/26) S-2101..2332 · S355JR"},
             "datum_z": 0, "grade": "S355JR", "unit_names": {k: v for k, v in UNITS}},
    "header": {"client": "ST. JOSEPH'S INSTITUTION INTERNATIONAL LTD", "project": "SJII - 1033 Upper Serangoon Road (Arup job 314457-00), tender",
               "description": "STRUCTURAL STEEL - FLOOR BEAMS, STEEL COLUMNS, TRUSSES, BONDEK PACKAGE (from 3D model, rev 2)",
               "contractor": "", "date": "14-11-2026"},
    "parts": out, "groups": groups,
    "layers": [dict({"k": k, "n": n, "c": c}, **({"off": True} if k == "bdk" else {})) for k, n, c in LAYERS],
    "units": [n for _, n in UNITS], "unitKeys": [k for k, _ in UNITS],
    "ghosts": extra["ghosts"], "gx": gx, "gy": gy, "profs": profs, "cats": cats,
    "notes": assumptions, "left": left, "assumptions": assumptions, "decisions": decisions, "cautions": cautions_mto,
    "noteSections": [
        {"title": "Basis", "items": [
            "Arup tender drawings T1 (30/10/26): GA plans Central Block S-2101..2108, Education ES S-2221..2229, HS S-2321..2332; general notes S-0001 / 0002; composite slab S-0033.",
            "Member tags are Yang's (UB beams, UC columns, BDK / SS / EF); the drawing mark (B45Q, B61V, ...) is kept as Ref and is searchable.",
            "One MTO unit per building and storey; building = tower; every beam is its own lift unit (single loose piece)."]},
        {"title": "Cautious (big member on a small support, or different sections butting)", "items": cautions or ["Nothing to flag."]},
        {"title": "Left out of the model", "from": "left"},
        {"title": "Decisions for Yang", "items": decisions},
        {"title": "Assumptions", "from": "assumptions"}],
}
json.dump(data, open(sys.argv[4], "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(f"{len(out)} parts, steel {kg_steel:,.0f} kg, {len(groups)} groups, {len(UNITS)} units; tags: "
      + ", ".join(f"{k} {v}" for k, v in sorted(count.items())))
print(f"cautious: {len(cautions)} pairs, {len(extra['cautions'])} joints")
print(f"trusses: {sum(tcount.values())} no., {truss_t:,.1f} t; tags " + ", ".join(f"{r}->{t}" for (f, r), t in tags.items() if f in ("TC", "BC", "W")))
print("mapping:", ", ".join(f"{k}->{v}" for k, v in mapping.items()))
