#!/usr/bin/env python3
"""Self-check for the sheet index (read_drawing.py index / crop) on a synthetic sheet:
frame + title block strip, two titled views with scales, a mark along a sloping member, a notes block.

    python tests/sheet_index_check.py
"""
import json
import sys
import tempfile
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sheet_index  # noqa: E402

tmp = Path(tempfile.mkdtemp())
doc = pymupdf.open()
pg = doc.new_page(width=1200, height=800)
pg.draw_rect(pymupdf.Rect(20, 20, 1180, 780), width=1)                 # frame
pg.draw_line((1000, 20), (1000, 780), width=1)                          # title block strip
for y, lab, val in ((600, "DRAWING NO. :", "T-100"), (640, "REV", "B"), (680, "PROJECT PHASE:", "TENDER")):
    pg.insert_text((1010, y), lab, fontsize=6)
    pg.insert_text((1010, y + 14), val, fontsize=9)
for x0, no, name, scale in ((80, "1", "PLAN AT LEVEL 2", "1 : 100"), (540, "1A", "SECTION A", "1 : 50")):
    pg.draw_rect(pymupdf.Rect(x0, 100, x0 + 300, 400), width=1)
    pg.insert_text((x0 + 100, 250), "9600", fontsize=7)
    pg.insert_text((x0 - 30, 452), no, fontsize=9)
    pg.insert_text((x0, 445), name, fontsize=9)
    pg.insert_text((x0, 458), scale, fontsize=7)
pg.insert_text((120, 180), "F-2BM-01", fontsize=7)
pg.draw_line((560, 380), (820, 120), width=1)
pg.insert_text((660, 270), "F-2BR-01", fontsize=7, morph=(pymupdf.Point(660, 270), pymupdf.Matrix(45)))
pg.insert_text((600, 150), "TOS +22.168", fontsize=7)
for k, t in enumerate(("NOTES:", "1. ALL STEEL TO BE GRADE S275.", "2. HOT-DIPPED GALVANIZED.")):
    pg.insert_text((80, 600 + 12 * k), t, fontsize=7)
pdf = tmp / "sheet.pdf"
doc.save(pdf)

sheet_index.build_index([pdf], tmp / "read")
s = json.loads((tmp / "read" / "sheets.json").read_text(encoding="utf-8"))["sheets"][0]
v = {x["id"]: x for x in s["views"]}
errs = []
tb = s["titleblock"]
if (tb.get("dwg_no"), tb.get("rev"), tb.get("status")) != ("T-100", "B", "TENDER"):
    errs.append(f"title block {tb}")
for vid, scale, want in (("1", "1:100", "F-2BM-01"), ("1A", "1:50", "F-2BR-01")):
    if vid not in v or v[vid]["scale"] != scale or want not in json.dumps(v[vid]["items"]):
        errs.append(f"view {vid}: {v.get(vid, {}).get('scale')} {v.get(vid, {}).get('items')}")
if "TOS +22.168" not in json.dumps(v.get("1A", {}).get("items", {}).get("levels", [])):
    errs.append("level not classified in 1A")
if not any("NOTES:" in x.get("rows", [""])[0] for x in s["views"] if not x["titled"]):
    errs.append("notes block not found")
sheet_index.build_index([pdf], tmp / "read2", prev=tmp / "read" / "sheets.json", thumbs=False)
if json.loads((tmp / "read2" / "sheets.json").read_text(encoding="utf-8"))["sheets"][0].get("changed") != "same":
    errs.append("unchanged sheet not marked same")
sheet_index.crop(tmp / "read", view="1A")
if not list((tmp / "read" / "crops").glob("*view1A*.png")):
    errs.append("crop not written")
print("sheet_index FAILED: " + "; ".join(errs) if errs else "sheet_index ok")
sys.exit(1 if errs else 0)
