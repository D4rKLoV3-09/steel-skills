#!/usr/bin/env python3
"""Retag UB4 to Yang's member tags (standing rule): t = Yang tag, ref = drawing mark, one-to-one.

    python tests/retag_ub4.py tests/fixtures/ub4.data.json OUT.data.json

Family by layer: chords TC/BC; truss diagonals and verticals W (truss web); cross beams and HSB
support beams UB; columns UC; plan and column-frame bracing BR; purlins P. Parts without a drawing
mark (PLT, US1) already carry Yang-style tags and keep them. Each family is numbered 1..n in
natural order of the drawing marks. Group names get the same replacement.
"""
import json
import re
import sys

FAMILY = {"Truss chords": None, "Truss diagonals": "W", "Verticals + posts": "W", "Cross beams + tiers": "UB",
          "Support beams (HSB)": "UB", "Columns": "UC", "Plan bracing": "BR", "Column frame bracing": "BR",
          "Roof purlins": "P"}


def natural(s):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]


def main(src, out):
    d = json.load(open(src, encoding="utf-8"))
    layers = [l["n"] for l in d["layers"]]
    marks = {}
    for p in d["parts"]:
        if not p["t"].startswith("X-UB"):
            continue
        lay = layers[p["layer"]]
        assert lay in FAMILY, f"no family for layer {lay} ({p['t']})"
        fam = FAMILY[lay] or ("TC" if re.search(r"-TC\d*$", p["t"]) else "BC")
        marks.setdefault(p["t"], fam)
    mapping, count = {}, {}
    for t in sorted(marks, key=natural):
        fam = marks[t]
        count[fam] = count.get(fam, 0) + 1
        mapping[t] = f"{fam}{count[fam]}"
    assert len(set(mapping.values())) == len(mapping), "mapping is not one-to-one"
    for p in d["parts"]:
        if p["t"] in mapping:
            p["ref"] = p["t"]
            p["t"] = mapping[p["t"]]
    pat = re.compile("|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)))
    for g in d["groups"]:
        g["name"] = pat.sub(lambda m: mapping[m.group(0)], g["name"])
    json.dump(d, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"{len(mapping)} drawing marks -> Yang tags: " + ", ".join(f"{k} {v}" for k, v in sorted(count.items())))
    for t in ("X-UB42-TC", "X-UB42-2DG02", "X-UB42-2VR01", "X-UB04-SC01", "X-UB41-PR01"):
        print(f"  {t} -> {mapping.get(t)}")
    return mapping


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
