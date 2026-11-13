#!/usr/bin/env python3
"""SJII: read every steel GA plan (vector PDF, 1:200) -> plan_members.json (mm, per sheet).

    python models/sjii/read_plans.py OUT.json

Per sheet: black member lines 0.9-1.4 pt wide (straight; arcs flattened into chords) paired with the
steel mark text beside them (parallel, within the line, <= 9 pt off); slab labels "<thk> BDK";
grid bubbles -> calibration (1:200 = 70.556 mm/pt, anchored on one bubble per axis).
Frames: CTB grid A1.. (X) / AA.. (Y); EDU (ES + HS sheets share grid B7) B1.. (X) / BA.. (Y).
"""
import json
import math
import re
import sys
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "generate-model"))
import read_drawing as rd  # noqa: E402

DIR = Path(__file__).resolve().parents[2] / "jobs" / "SJII" / "Drawings" / "Steel Structure Drawings"
MMPT = 25.4 / 72 * 200
MARK = re.compile(r"^(B\d{2,3}[A-Z]{1,2}|R20A|C3\d[A-Z]{1,2}|BU\d\d|S[235]0[A-Z]|D40H|SC01)$")
# FFL (m) from the architectural sections SJI-DPA-ZZ-XX-DR-A-2001 (CTB) and SJII-DPA-ES / HS-XX-DR-A-2001 (EDU)
CTB = {"01": 8.70, "02": 15.00, "03": 20.25, "04": 28.10, "05": 33.35, "06": 38.60, "LR": 43.85, "UR": 49.10}
EDU = {"01": 9.75, "02": 15.00, "03": 20.25, "04": 25.50, "05": 30.00, "06": 34.50, "07": 39.00, "08": 43.50,
       "09": 48.00, "10": 52.50, "LR": 57.00, "UR": 63.50}
# grid positions (mm) - all bays 9000 as dimensioned, BM-BN 4500
GX = {**{f"A{i}": (i - 1) * 9000 for i in range(1, 13)}, **{f"B{i}": (i - 1) * 9000 for i in range(1, 19)}}
GY = {**{f"A{c}": i * 9000 for i, c in enumerate("ABCDEFGHJ")}}
_y = 0
for c in "ABCDEFGHJKLMNPQR":
    GY["B" + c] = _y
    _y += 4500 if c == "M" else 9000


def sheets():
    for f in sorted(DIR.glob("SJI-ARP-*-DR-S-2*-T1.pdf")):
        m = re.match(r"SJI-ARP-(CTB|ES|HS)-(\w\w)-DR", f.name)
        if not m:
            continue
        b, lv = m.groups()
        tab = CTB if b == "CTB" else EDU
        if lv in tab:
            yield b, lv, tab[lv], f


WMIN, WMAX = 0.9, 1.4      # beams 0.96 or 1.32 pt (columns / walls 1.32 stay unlabelled)


def merge(page, region, gap=2.0, atol=0.6, otol=0.4):
    """Collinear black pieces joined: cluster by angle, then by offset, then join overlapping intervals."""
    x0, y0, x1, y1 = region
    segs = []
    for a in rd.segments(page):
        if not (WMIN <= a[4] <= WMAX) or math.hypot(a[2] - a[0], a[3] - a[1]) < 0.3:
            continue
        if not (x0 < min(a[0], a[2]) and max(a[0], a[2]) < x1 and y0 < min(a[1], a[3]) and max(a[1], a[3]) < y1):
            continue
        segs.append((math.degrees(math.atan2(a[3] - a[1], a[2] - a[0])) % 180, a))
    segs.sort()
    groups, cur = [], []
    for g in segs:                                   # angle clusters (0 / 180 wrap joined below)
        if cur and g[0] - cur[-1][0] > atol:
            groups.append(cur); cur = []
        cur.append(g)
    if cur:
        groups.append(cur)
    if len(groups) > 1 and groups[-1][-1][0] > 180 - atol and groups[0][0][0] < atol:
        groups[0] = [(d - 180, a) for d, a in groups.pop()] + groups[0]
    out = []
    for grp in groups:
        ang = math.radians(sum(d for d, _ in grp) / len(grp))
        c, s = math.cos(ang), math.sin(ang)
        iv = sorted(((-a[0] * s + a[1] * c), *sorted((a[0] * c + a[1] * s, a[2] * c + a[3] * s))) for _, a in grp)
        rows, row = [], []
        for v in iv:
            if row and v[0] - row[-1][0] > otol:
                rows.append(row); row = []
            row.append(v)
        rows.append(row)
        for row in rows:
            o = sum(v[0] for v in row) / len(row)
            row.sort(key=lambda v: v[1])
            lo, hi = row[0][1], row[0][2]
            for _, t0, t1 in row[1:] + [(0, 1e18, 1e18)]:
                if t0 <= hi + gap:
                    hi = max(hi, t1)
                    continue
                out.append([lo * c - o * s, lo * s + o * c, hi * c - o * s, hi * s + o * c])
                lo, hi = t0, t1
    return out


def chains(lines, tol=0.8, amax=25):
    """Short pieces meeting end to end at a small angle = one curved member (polyline). Returns chain id per line."""
    n = len(lines)
    par = list(range(n))

    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    short = [i for i, m in enumerate(lines) if math.hypot(m[2] - m[0], m[3] - m[1]) < 40]
    cell = {}
    for i in short:
        m = lines[i]
        for e in (m[:2], m[2:]):
            cell.setdefault((round(e[0] / 2), round(e[1] / 2)), []).append(i)
    ang = lambda m: math.degrees(math.atan2(m[3] - m[1], m[2] - m[0])) % 180
    for i in short:
        m = lines[i]
        for e in (m[:2], m[2:]):
            kx, ky = round(e[0] / 2), round(e[1] / 2)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in cell.get((kx + dx, ky + dy), []):
                        if j <= i:
                            continue
                        q = lines[j]
                        if min(math.dist(e, q[:2]), math.dist(e, q[2:])) > tol:
                            continue
                        da = abs(ang(m) - ang(q)) % 180
                        if 0.6 < min(da, 180 - da) < amax:
                            par[f(i)] = f(j)
    return [f(i) for i in range(n)]


def polyline(pieces):
    """Order chained pieces into one point list."""
    segs = [((m[0], m[1]), (m[2], m[3])) for m in pieces]
    pts = list(segs.pop(0))
    while segs:
        for k, (p, q) in enumerate(segs):
            if math.dist(p, pts[-1]) < 1: pts.append(q)
            elif math.dist(q, pts[-1]) < 1: pts.append(p)
            elif math.dist(q, pts[0]) < 1: pts.insert(0, p)
            elif math.dist(p, pts[0]) < 1: pts.insert(0, q)
            else: continue
            segs.pop(k); break
        else:
            break
    return pts


def labels(page, region):
    x0, y0, x1, y1 = region
    out = []
    for blk in page.get_text("dict")["blocks"]:
        for ln in blk.get("lines", []):
            for sp in ln["spans"]:
                for t in sp["text"].split():
                    bb = sp["bbox"]
                    cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
                    if MARK.match(t) and x0 < cx < x1 and y0 < cy < y1:
                        out.append((t, cx, cy, ln["dir"]))
    return out


def arcs(page, region, wmin, wmax):
    """Black bezier pieces flattened to 6 chords each (curved edge beams)."""
    x0, y0, x1, y1 = region
    out = []
    for d in page.get_drawings():
        col = d.get("color") or ()
        if (col and max(col) > 0.1) or not (wmin <= (d.get("width") or 0) <= wmax):
            continue
        for it in d["items"]:
            if it[0] != "c":
                continue
            P = [(p.x, p.y) for p in it[1:5]]
            if not all(x0 < x < x1 and y0 < y < y1 for x, y in P) or math.dist(P[0], P[3]) < 15:
                continue
            pts = []
            for k in range(7):
                t = k / 6
                c = [(1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3]
                pts.append((sum(c[i] * P[i][0] for i in range(4)), sum(c[i] * P[i][1] for i in range(4))))
            out.append(pts)
    return out


def read(b, lv, ffl, f):
    page = fitz.open(f)[0]
    words = page.get_text("words")
    pat = r"^A(\d{1,2}|[A-J])$" if b == "CTB" else r"^B(\d{1,2}|[A-R])$"
    bub = {}
    for w in words:
        if re.match(pat, w[4]) and (w[2] - w[0]) < 45:
            bub.setdefault(w[4], ((w[0] + w[2]) / 2, (w[1] + w[3]) / 2))
    xs = {k: v[0] for k, v in bub.items() if k in GX}
    ys = {k: v[1] for k, v in bub.items() if k in GY}
    kx = "B7" if "B7" in xs else ("A1" if b == "CTB" else min(xs, key=lambda k: GX[k]))
    ky = min(ys, key=lambda k: GY[k])
    # check every other bubble against the 9000 grid (flags a wrong scale / grid)
    err = max([abs(GX[kx] + (xs[k] - xs[kx]) * MMPT - GX[k]) for k in xs if k != "A9"] +
              [abs(GY[ky] + (ys[ky] - ys[k]) * MMPT - GY[k]) for k in ys])
    X = lambda px: round(GX[kx] + (px - xs[kx]) * MMPT, 1)
    Y = lambda py: round(GY[ky] + (ys[ky] - py) * MMPT, 1)
    # plan area: inside the grid bubbles, left of the schedules
    region = (min(xs.values()) - 220, min(ys.values()) - 220, min(max(xs.values()) + 260, 2680), max(ys.values()) + 60)
    lab = labels(page, region)
    lines = merge(page, region)
    lines = [m for m in lines if math.hypot(m[2] - m[0], m[3] - m[1]) > 2]
    ch = chains(lines)
    clen = {}
    for i, m in enumerate(lines):
        clen[ch[i]] = clen.get(ch[i], 0) + math.hypot(m[2] - m[0], m[3] - m[1])
    curves = arcs(page, region, WMIN, WMAX)
    # each label picks its nearest parallel line; each line keeps its nearest label
    own = {}
    for t, cx, cy, d in lab:
        best = None
        for i, m in enumerate(lines):
            dx, dy = m[2] - m[0], m[3] - m[1]
            L = math.hypot(dx, dy)
            tx, ty = dx / L, dy / L
            if abs(tx * d[0] + ty * d[1]) < 0.97:
                continue
            s = (cx - m[0]) * tx + (cy - m[1]) * ty
            dist = abs(-(cx - m[0]) * ty + (cy - m[1]) * tx)
            if -2 <= s <= L + 2 and dist < 9 and clen[ch[i]] > 6 and (best is None or dist < best[0]):
                best = (dist, ch[i])
        if best is None:          # curved beam: nearest arc within 12 pt
            for j, pts in enumerate(curves):
                dist = min(math.dist((cx, cy), p) for p in pts)
                if dist < 12 and (best is None or dist < best[0]):
                    best = (dist, ("c", j))
        if best and (best[1] not in own or own[best[1]][0] > best[0]):
            own[best[1]] = (best[0], t)
        elif best is None:
            own.setdefault(("free", cx, cy), (0, t))
    mem, free = [], []
    for k, (_, t) in own.items():
        if isinstance(k, int):
            pcs = [m for i, m in enumerate(lines) if ch[i] == k]
            if len(pcs) == 1:
                m = pcs[0]
                mem.append({"mark": t, "a": [X(m[0]), Y(m[1])], "b": [X(m[2]), Y(m[3])]})
                continue
            pts = polyline(pcs)
            step = max(1, round(len(pts) / 12))       # about 12 chords per curved member
            pts = pts[::step] + ([pts[-1]] if (len(pts) - 1) % step else [])
            for p, q in zip(pts, pts[1:]):
                mem.append({"mark": t, "a": [X(p[0]), Y(p[1])], "b": [X(q[0]), Y(q[1])], "arc": True})
        elif k[0] == "c":
            pts = curves[k[1]]
            for p, q in zip(pts, pts[1:]):
                mem.append({"mark": t, "a": [X(p[0]), Y(p[1])], "b": [X(q[0]), Y(q[1])], "arc": True})
        else:
            free.append({"mark": t, "at": [X(k[1]), Y(k[2])]})
    # slab thickness labels "<thk>" directly above "BDK"
    bdk = []
    for w in words:
        if w[4] == "BDK" and region[0] < w[0] < region[2] and region[1] < w[1] < region[3]:
            for v in words:
                if re.match(r"^\d{3}$", v[4]) and abs((v[0] + v[2]) / 2 - (w[0] + w[2]) / 2) < 8 and 0 < w[1] - v[3] < 6:
                    bdk.append({"thk": int(v[4]), "at": [X((w[0] + w[2]) / 2), Y(w[1])]})
    # column outlines (RC circles / rectangles and small steel columns): closed paths 4-30 pt across
    cols = []
    for d in page.get_drawings():
        r = d["rect"]
        if not (region[0] < r.x0 < region[2] and region[1] < r.y0 < region[3]) or not (4 < r.width < 30 and 4 < r.height < 30):
            continue
        if not (d.get("closePath") or d.get("fill") or len(d["items"]) > 6) or max(r.width, r.height) > 2.2 * min(r.width, r.height):
            continue
        c = [X((r.x0 + r.x1) / 2), Y((r.y0 + r.y1) / 2)]
        if all(math.dist(c, q["c"]) > 150 for q in cols):
            cols.append({"c": c, "s": [round(r.width * MMPT), round(r.height * MMPT)], "fill": bool(d.get("fill"))})
    unl = len({ch[i] for i in range(len(lines)) if ch[i] not in own})
    print(f"{b}-{lv} FFL {ffl:.2f}: {len(mem)} members, {len(free)} unpaired marks, {unl} unlabelled lines, "
          f"{len(bdk)} BDK labels, {len(cols)} column outlines, grid check {err:.0f} mm")
    return {"bldg": b, "lv": lv, "ffl": ffl, "sheet": f.stem, "members": mem, "free": free, "bdk": bdk, "cols": cols,
            "unlabelled": [[X(m[0]), Y(m[1]), X(m[2]), Y(m[3])] for i, m in enumerate(lines) if ch[i] not in own]}


if __name__ == "__main__":
    out = [read(*s) for s in sheets()]
    json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), indent=0)
