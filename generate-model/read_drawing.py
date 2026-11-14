#!/usr/bin/env python3
"""Fast reader for vector PDF drawings (PyMuPDF). Replaces hand-cropping and eyeballing.

    python read_drawing.py index   PDF_OR_FOLDER [...] --out DIR [--prev OLD/sheets.json]
                                   START HERE: index.md = every sheet as text (title block, views, marks, sizes,
                                   levels, dims; about 1 k tokens per A1 sheet), sheets.json, thumbnails
    python read_drawing.py crop    DIR --view ID | --find TEXT | --box x0 y0 x1 y1 [--part tl|tr|bl|br] [--max-px 1400]
                                   one view / one mark as an image (sheet_index.py has the details)
    python read_drawing.py info    PDF OUTDIR                     page sizes, text per page, overview PNGs
    python read_drawing.py words   PDF PAGE REGEX [x0 y0 x1 y1]   words matching REGEX with centre (pt)
    python read_drawing.py render  PDF PAGE x0 y0 x1 y1 DPI OUT   crop to PNG (only to settle an ambiguity)
    python read_drawing.py members PDF PAGE x0 y0 x1 y1 OUT.json [--wmin 0.9] [--wmax 99] [--minlen 15]
                                   member lines (dashes merged) each paired with its parallel mark label

Coordinates are PDF points (y down). Calibrate once per view: scale = known dim / pt distance
between two grid lines, then X = (px - px_grid) * scale, Y = (py_grid - py) * scale. Levels in a
section: two known levels (FFL / TOS / BOB markers) give z(py) the same way.
Member lines: black only (grey = existing / by others), width >= wmin. Labels: text lines starting
with --prefix (default "X-"), matched when parallel (|cos| > 0.97), within the line's length and
<= 9 pt off it.
"""
import argparse
import json
import math
import re
from pathlib import Path

import fitz  # PyMuPDF (pypdf / poppler are not installed on Yang's PC)


def segments(page):
    """Every straight black segment: (x0, y0, x1, y1, width)."""
    out = []
    for d in page.get_drawings():
        col = d.get("color") or ()
        if col and max(col) > 0.1:
            continue
        w = d.get("width") or 0
        for it in d["items"]:
            if it[0] == "l":
                out.append((it[1].x, it[1].y, it[2].x, it[2].y, w))
            elif it[0] == "re":
                r = it[1]
                out += [(r.x0, r.y0, r.x1, r.y0, w), (r.x1, r.y0, r.x1, r.y1, w),
                        (r.x1, r.y1, r.x0, r.y1, w), (r.x0, r.y1, r.x0, r.y0, w)]
    return out


def merged(page, region, wmin=0.9, wmax=99, gap=12, ang_tol=0.6, off_tol=0.4):
    """Join collinear pieces (dashed / broken lines) into one line each."""
    x0, y0, x1, y1 = region
    lines = []      # [angle, origin, lo, hi]
    for a in segments(page):
        if not (wmin <= a[4] <= wmax) or math.hypot(a[2] - a[0], a[3] - a[1]) < 1:
            continue
        if not (x0 < min(a[0], a[2]) and max(a[0], a[2]) < x1 and y0 < min(a[1], a[3]) and max(a[1], a[3]) < y1):
            continue
        lines.append(_line(a[:2], a[2:4]))
    changed = True
    while changed:              # merge until stable (pieces can arrive in any order)
        changed = False
        for i in range(len(lines)):
            for j in range(i + 1, len(lines)):
                m = _join(lines[i], lines[j], gap, ang_tol, off_tol)
                if m:
                    lines[i] = m
                    del lines[j]
                    changed = True
                    break
            if changed:
                break
    return [_ends(g) for g in lines]


def _line(p, q):
    ang = math.atan2(q[1] - p[1], q[0] - p[0]) % math.pi
    t = (q[0] - p[0]) * math.cos(ang) + (q[1] - p[1]) * math.sin(ang)
    return [ang, p, min(0, t), max(0, t)]


def _ends(g):
    ang, p, lo, hi = g
    c, s = math.cos(ang), math.sin(ang)
    return (p[0] + lo * c, p[1] + lo * s, p[0] + hi * c, p[1] + hi * s)


def _join(g, h, gap, ang_tol, off_tol):
    if abs((math.degrees(g[0] - h[0]) + 90) % 180 - 90) > ang_tol:
        return None
    c, s = math.cos(g[0]), math.sin(g[0])
    e = _ends(h)
    pts = [e[:2], e[2:]]
    if max(abs(-(x - g[1][0]) * s + (y - g[1][1]) * c) for x, y in pts) > off_tol:
        return None
    t = [(x - g[1][0]) * c + (y - g[1][1]) * s for x, y in pts]
    if min(t) > g[3] + gap or max(t) < g[2] - gap:
        return None
    return [g[0], g[1], min(g[2], *t), max(g[3], *t)]


def labels(page, region, prefix="X-"):
    """Text lines starting with prefix: (text, cx, cy, direction). Run-together marks are split."""
    x0, y0, x1, y1 = region
    out = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = "".join(s["text"] for s in ln["spans"]).strip()
            bb = ln["bbox"]
            cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            if x0 < cx < x1 and y0 < cy < y1 and t.startswith(prefix):
                for part in re.split(rf"\s*(?={re.escape(prefix)})", t):
                    if part.strip():
                        out.append((part.strip(), cx, cy, ln["dir"]))
    return out


def members(page, region, wmin=0.9, wmax=99, minlen=15, maxd=9, prefix="X-"):
    lab = labels(page, region, prefix)
    res = []
    for m in merged(page, region, wmin, wmax):
        dx, dy = m[2] - m[0], m[3] - m[1]
        L = math.hypot(dx, dy)
        if L <= minlen:
            continue
        tx, ty = dx / L, dy / L
        best = None
        for t, cx, cy, d in lab:
            if abs(tx * d[0] + ty * d[1]) < 0.97:
                continue
            s = (cx - m[0]) * tx + (cy - m[1]) * ty
            dist = abs(-(cx - m[0]) * ty + (cy - m[1]) * tx)
            if -2 <= s <= L + 2 and dist < maxd and (best is None or dist < best[0]):
                best = (dist, t)
        res.append({"line": [round(v, 2) for v in m], "len": round(L, 2), "mark": best[1] if best else None})
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("info"); s.add_argument("pdf"); s.add_argument("outdir")
    s = sub.add_parser("words"); s.add_argument("pdf"); s.add_argument("page", type=int); s.add_argument("regex")
    s.add_argument("box", nargs="*", type=float)
    s = sub.add_parser("render"); s.add_argument("pdf"); s.add_argument("page", type=int)
    s.add_argument("box", nargs=4, type=float); s.add_argument("dpi", type=int); s.add_argument("out")
    s = sub.add_parser("members"); s.add_argument("pdf"); s.add_argument("page", type=int)
    s.add_argument("box", nargs=4, type=float); s.add_argument("out")
    for k, v in (("--wmin", 0.9), ("--wmax", 99.0), ("--minlen", 15.0)):
        s.add_argument(k, type=float, default=v)
    s.add_argument("--prefix", default="X-")
    s = sub.add_parser("index"); s.add_argument("inputs", nargs="+"); s.add_argument("--out", required=True)
    s.add_argument("--prev"); s.add_argument("--no-thumbs", action="store_true")
    s = sub.add_parser("crop"); s.add_argument("read_dir"); s.add_argument("--view"); s.add_argument("--find")
    s.add_argument("--box", nargs=4, type=float); s.add_argument("--sheet"); s.add_argument("--pad", type=float, default=25)
    s.add_argument("--max-px", type=int, default=1400); s.add_argument("--dpi", type=int); s.add_argument("--part", choices=["tl", "tr", "bl", "br"])
    a = ap.parse_args()
    if a.cmd in ("index", "crop"):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import sheet_index
        if a.cmd == "index":
            return sheet_index.build_index(a.inputs, a.out, a.prev, not a.no_thumbs)
        if not (a.view or a.find or a.box):
            ap.error("crop needs --view, --find or --box")
        return sheet_index.crop(a.read_dir, a.view, a.find, a.box, a.sheet, a.pad, a.max_px, a.dpi, a.part)
    doc = fitz.open(a.pdf)
    if a.cmd == "info":
        out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
        for i, pg in enumerate(doc):
            (out / f"p{i + 1}.txt").write_text(pg.get_text(), encoding="utf-8")
            pg.get_pixmap(dpi=40).save(str(out / f"p{i + 1}_overview.png"))
            print(f"page {i + 1}: {pg.rect.width:.0f} x {pg.rect.height:.0f} pt, {len(pg.get_drawings())} drawings, "
                  f"{len(pg.get_images())} images{' (scanned: read the image)' if pg.get_images() and not pg.get_drawings() else ''}")
    elif a.cmd == "words":
        box = a.box or [-1e9, -1e9, 1e9, 1e9]
        for w in doc[a.page - 1].get_text("words"):
            cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
            if re.search(a.regex, w[4]) and box[0] < cx < box[2] and box[1] < cy < box[3]:
                print(f"{cx:8.1f} {cy:8.1f}  {w[4]}")
    elif a.cmd == "render":
        doc[a.page - 1].get_pixmap(dpi=a.dpi, clip=fitz.Rect(*a.box)).save(a.out)
    else:
        res = members(doc[a.page - 1], a.box, a.wmin, a.wmax, a.minlen, prefix=a.prefix)
        Path(a.out).write_text(json.dumps(res, indent=0), encoding="utf-8")
        marks = {}
        for r in res:
            marks[r["mark"]] = marks.get(r["mark"], 0) + 1
        print(f"{len(res)} lines -> {a.out}; per mark: " + ", ".join(f"{k} {v}" for k, v in sorted(marks.items(), key=lambda kv: str(kv[0]))))


if __name__ == "__main__":
    main()
