#!/usr/bin/env python3
"""ga_plan.connect on a small drawn plan: every end reaches its neighbour, Cautious joints are returned.

    python tests/ga_plan_check.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import ga_plan as gp  # noqa: E402

P = {"big": {"type": "I", "h": 600, "b": 300, "tw": 12, "tf": 20, "kgm": 150},
     "small": {"type": "I", "h": 300, "b": 150, "tw": 7, "tf": 11, "kgm": 40}}
B = lambda i, a, b, p: {"id": i, "a": list(a), "b": list(b), "prof": p}
beams = [B("A1", (0, 0), (4000, 0), "big"),            # starts 500 short of a round column, ends 500 short of A2
         B("A2", (5000, 0), (9000, 0), "big"),         # in line with A1, far end has no neighbour
         B("R", (4500, 600), (4500, 5000), "small"),   # drawn 600 short of the A line, over the gap
         B("S", (6000, -3000), (12000, -3000), "small"),
         B("D", (8000, -600), (8000, -2400), "big")]   # deep beam between A2 and the small S
beams += [B("E1", (20000, 0), (26000, 0), "big"), B("E2", (23000, -3000), (23000, 3000), "small"),     # drawn through each other
          B("G1", (40300, 0), (45000, 0), "big"), B("G2", (40250, 150), (44000, 2400), "big")]        # fan out from one column
cols = [{"c": [-500, 0], "s": [600, 600], "round": True}, {"c": [40000, 0], "s": [600, 600], "round": True}]
cautions, opened = gp.connect(beams, cols, P)
m = {b["id"]: b for b in beams}
checks = [
    ("A1 runs to the column face", m["A1"]["a"] == [-200.0, 0.0] and m["A1"]["end_kind"][0] == "col"),
    ("A1 and A2 butt at mid-gap", m["A1"]["b"] == [4500.0, 0.0] == m["A2"]["a"] and m["A1"]["end_kind"][1] == "butt"),
    ("R runs to the A line and is coped", m["R"]["a"] == [4500.0, 0.0] and m["R"]["ends"][0][0]["face"] == "cope"),
    ("D joins A2 and S", m["D"]["a"] == [8000.0, 0.0] and m["D"]["b"] == [8000.0, -3000.0]),
    ("end with no neighbour stays free", m["A2"]["end_kind"][1] == "free" and m["A2"]["b"] == [9000, 0]),
    ("Cautious: deep D on shallow S only", cautions == [{"k": "deep", "bm": "D", "on": "S"}]),
    ("the shallower of two crossing lines is cut and coped both sides", "E2.2" in m and m["E2"]["b"] == [23000.0, 0.0] == m["E2.2"]["a"]
     and m["E2"]["ends"][1][0]["host"] == "E1" == m["E2.2"]["ends"][0][0]["host"] and m["E1"]["a"] == [20000, 0]),
    ("beams fanning out from one column are mitred", all(m[i]["end_kind"][0] == "col" and len(m[i]["ends"][0]) == 2 for i in ("G1", "G2"))
     and m["G1"]["ends"][0][1] == m["G2"]["ends"][0][1]),
    ("no open joints, no helper keys left", opened == [] and not any(k.startswith("_") for b in beams for k in b)),
]
for name, ok in checks:
    print("OK  " if ok else "FAIL", name)
sys.exit(0 if all(ok for _, ok in checks) else 1)
