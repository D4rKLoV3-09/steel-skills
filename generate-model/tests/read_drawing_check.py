#!/usr/bin/env python3
"""Self-check for read_drawing.py on a synthetic PDF: a dashed beam line with its mark, a vertical
column line with a rotated mark, a grey line that must be ignored.

    python tests/read_drawing_check.py
"""
import sys
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from read_drawing import members  # noqa: E402

doc = fitz.open()
pg = doc.new_page(width=600, height=400)
for x in range(50, 450, 40):                                     # dashed horizontal beam, 30 pt dashes
    pg.draw_line((x, 100), (x + 30, 100), width=1.0)
pg.insert_text((200, 95), "X-B01", fontsize=6)
pg.draw_line((500, 50), (500, 350), width=1.0)                    # vertical column
pg.insert_text((495, 250), "X-C01", fontsize=6, rotate=90)
pg.draw_line((50, 300), (450, 300), width=1.0, color=(0.6, 0.6, 0.6))   # grey: existing, ignored
res = members(pg, (0, 0, 600, 400))
got = sorted((r["mark"], round(r["len"])) for r in res)
assert got == [("X-B01", 390), ("X-C01", 300)], got
print("read_drawing ok:", got)
