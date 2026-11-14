#!/usr/bin/env python3
"""Look at one part of a drawing sheet instead of the whole sheet.

    python crop.py READ_DIR --view 2A                  one view found by read_drawings.py (id from index.md)
    python crop.py READ_DIR --find F-2FAPT2-SC-01      around every place this text occurs (one image per view)
    python crop.py READ_DIR --box 950 550 1400 1030    a box in sheet points (from sheets.json)
    options: --sheet NAME (needed only when the job has several sheets with that view id / text)
             --pad 25 (pt around the box)   --max-px 1400 (long side; raise only if a detail is unreadable)
             --dpi N (fixed dpi instead of fitting to --max-px)   --part tl|tr|bl|br (one quarter, twice the detail)

READ_DIR is the --out folder of read_drawings.py. Prints the PNG path, the dpi used and, for a view with a
scale, how many real mm one pixel is (for a dimension that has to be scaled off: mark it as scaled).
Needs poppler (pdftoppm).
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys


def scale_of(v):
    m = re.match(r"1:(\d+(?:\.\d+)?)$", v.get("scale") or "")
    return float(m.group(1)) if m else None


def render(sheet, box, out, max_px, dpi, label, scale):
    W, H = sheet["size_pt"]
    x0, y0, x1, y1 = max(0, box[0]), max(0, box[1]), min(W, box[2]), min(H, box[3])
    if not dpi:
        dpi = int(min(300, max_px / max(x1 - x0, y1 - y0) * 72))
    k = dpi / 72
    stem = out / re.sub(r"[^A-Za-z0-9_.-]+", "_", f'{sheet["sheet"]}_{label}_{dpi}dpi')
    subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(sheet["page"]), "-l", str(sheet["page"]), "-singlefile", "-png",
                    "-x", str(int(x0 * k)), "-y", str(int(y0 * k)), "-W", str(int((x1 - x0) * k)), "-H", str(int((y1 - y0) * k)),
                    sheet["file"], str(stem)], check=True)
    note = f", 1 px = {scale * 25.4 / dpi:.2f} mm real (scale 1:{scale:g})" if scale else ""
    print(f"{stem}.png  {int((x1 - x0) * k)}x{int((y1 - y0) * k)} px, {dpi} dpi{note}, box {[round(v) for v in (x0, y0, x1, y1)]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("read_dir")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--view")
    g.add_argument("--find")
    g.add_argument("--box", nargs=4, type=float)
    ap.add_argument("--sheet")
    ap.add_argument("--pad", type=float, default=25)
    ap.add_argument("--max-px", type=int, default=1400)
    ap.add_argument("--dpi", type=int)
    ap.add_argument("--part", choices=["tl", "tr", "bl", "br"])
    a = ap.parse_args()
    rd = pathlib.Path(a.read_dir)
    sheets = json.loads((rd / "sheets.json").read_text(encoding="utf-8"))["sheets"]
    if a.sheet:
        sheets = [s for s in sheets if s["sheet"] == a.sheet]
    out = rd / "crops"
    out.mkdir(exist_ok=True)

    def quarter(b):
        if not a.part:
            return b
        mx, my = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        ov = 0.06 * max(b[2] - b[0], b[3] - b[1])               # overlap so nothing is cut at the seam
        return [b[0] if a.part[1] == "l" else mx - ov, b[1] if a.part[0] == "t" else my - ov,
                mx + ov if a.part[1] == "l" else b[2], my + ov if a.part[0] == "t" else b[3]]

    def padded(b):
        return [b[0] - a.pad, b[1] - a.pad, b[2] + a.pad, b[3] + a.pad]

    n = 0
    for s in sheets:
        if a.box:
            render(s, quarter(a.box), out, a.max_px, a.dpi, "box" + (a.part or ""), None)
            n += 1
            continue
        for v in s["views"]:
            if a.view:
                if v["id"].lower() == a.view.lower():
                    render(s, quarter(padded(v["box"])), out, a.max_px, a.dpi, "view" + v["id"] + (a.part or ""), scale_of(v))
                    n += 1
            else:
                hits = [w["box"] for w in v["words"] if a.find.lower() in w["t"].lower()]
                if hits:
                    b = [min(h[0] for h in hits) - 90, min(h[1] for h in hits) - 90,
                         max(h[2] for h in hits) + 90, max(h[3] for h in hits) + 90]
                    render(s, padded(b), out, a.max_px, a.dpi, f'find_{a.find}_in_{v["id"]}', scale_of(v))
                    n += 1
    if not n:
        ids = ", ".join(f'{s["sheet"]}: ' + " ".join(v["id"] for v in s["views"]) for s in sheets)
        sys.exit(f"nothing matched. Views: {ids}")


if __name__ == "__main__":
    main()
