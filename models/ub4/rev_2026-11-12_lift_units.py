#!/usr/bin/env python3
"""UB4 revision 12-11-2026 (Yang): lift units.

    python rev_2026-11-12_lift_units.py IN.data.json OUT.data.json

1. The cross beams SB-05..SB-08 (and the strut on them) over the box tower at the west end of UB41
   sit on the box tower: move them from lift unit "Truss UB41" to "Box tower FB-BS2" (tower and MTO
   sheet "Columns + frames"). Truss UB41 keeps the truss that bears on the column corbel, incl. its
   end verticals (W11, X-UB41-2VR01).
2. The "Columns + frames" tower reads "Columns" in the selection chain (group label).
"""
import json
import sys

import numpy as np

BOX_X_MAX = 34300.0     # east edge of the box tower FB-BS2 (x 30,801..34,271 mm)


def main(src, out):
    d = json.load(open(src, encoding="utf-8"))
    G = d["groups"]
    find = lambda level, name: next(i for i, g in enumerate(G) if g["level"] == level and g["name"] == name)
    lu_ub41, lu_box = find("lift", "Truss UB41"), find("lift", "Box tower FB-BS2")
    tw_cols = find("tower", "Columns + frames")
    unit_cols = d["units"].index("Columns + frames")
    moved = []
    for p in d["parts"]:
        if p["lu"] != lu_ub41 or p["t"].startswith("W"):
            continue
        cx = np.mean([v[0] for pr in p["pr"] for f in pr for v in f])
        if cx < BOX_X_MAX:
            p["lu"], p["tw"], p["unit"] = lu_box, tw_cols, unit_cols
            moved.append(p)
    G[tw_cols]["label"] = "Columns"
    json.dump(d, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    tags = sorted({p["t"] for p in moved}, key=lambda t: (t.rstrip("0123456789"), int(t[len(t.rstrip("0123456789")):] or 0)))
    print(f"moved {len(moved)} parts ({sum(p['kg'] for p in moved):,.1f} kg) from Truss UB41 to Box tower FB-BS2: {', '.join(tags)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
