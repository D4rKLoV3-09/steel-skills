#!/usr/bin/env python3
"""GA floor plans (vector PDF) -> connected floor framing: the reusable part of a plan job.
The job's own script keeps only its numbers (sheet list, mark pattern, levels, grids, schedule) - see models/sjii/.

Reading (PDF points):
  merge(page, region, wmin, wmax)   black line pieces of the member line width joined into member lines
  chains(lines) / polyline(pieces)  curved member = chain of short pieces
  labels(page, region, pattern)     mark texts with their direction
  arcs(page, region, wmin, wmax)    bezier curves as chords
  pair(lines, ch, lab, curves)      each mark -> its nearest parallel line
  outlines(page, region)            column outlines, round or rectangular
  bands(lines)                      members drawn as outlines on an elevation (truss chords, verticals, diagonals)
Framing (mm):
  connect(beams, cols, profiles)    every beam end runs to its neighbour (rule below); returns the Cautious joints
  bondek(...)                       deck strips, edgeform, stud rows (Yang's bondek package)

Connection rule (Yang): a plan draws member lines short of each other, but steel never floats. Each end runs along
its axis to the nearest neighbour within REACH: a column (to its face), a crossing beam (to its axis, coped; at a
node the deepest line is the host and runs through), or the beam in line with it (butt joint at mid-gap).
Cautious joints: a member deeper than its support, wider than its column, or butting a different section.
"""
import math

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

import read_drawing as rd

REACH, BACK = 1500, 300      # mm an end may run forward / be pulled back to reach its neighbour


def merge(page, region, wmin, wmax, gap=2.0, atol=0.6, otol=0.4):
    """Collinear black pieces joined: cluster by angle, then by offset, then join overlapping intervals."""
    x0, y0, x1, y1 = region
    segs = []
    for a in rd.segments(page):
        if not (wmin <= a[4] <= wmax) or math.hypot(a[2] - a[0], a[3] - a[1]) < 0.3:
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


def labels(page, region, pattern):
    x0, y0, x1, y1 = region
    out = []
    for blk in page.get_text("dict")["blocks"]:
        for ln in blk.get("lines", []):
            for sp in ln["spans"]:
                for t in sp["text"].split():
                    bb = sp["bbox"]
                    cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
                    if pattern.match(t) and x0 < cx < x1 and y0 < cy < y1:
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


def pair(lines, ch, lab, curves, off=9):
    """Each mark picks its nearest parallel line (or curve within 12 pt); each line keeps its nearest mark.
    -> members [{"mark", "pts"}] (2 points = straight, more = curved chords), free [(mark, x, y)], used chain ids."""
    clen = {}
    for i, m in enumerate(lines):
        clen[ch[i]] = clen.get(ch[i], 0) + math.hypot(m[2] - m[0], m[3] - m[1])
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
            if -2 <= s <= L + 2 and dist < off and clen[ch[i]] > 6 and (best is None or dist < best[0]):
                best = (dist, ch[i])
        if best is None:
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
                mem.append({"mark": t, "pts": [tuple(pcs[0][:2]), tuple(pcs[0][2:])]})
                continue
            pts = polyline(pcs)
            step = max(1, round(len(pts) / 12))       # about 12 chords per curved member
            mem.append({"mark": t, "pts": pts[::step] + ([pts[-1]] if (len(pts) - 1) % step else [])})
        elif k[0] == "c":
            mem.append({"mark": t, "pts": curves[k[1]]})
        else:
            free.append((t, k[1], k[2]))
    return mem, free, {k for k in own if isinstance(k, int)}


def outlines(page, region, lo=4, hi=30):
    """Column outlines: filled or closed paths lo..hi pt across (white text masks skipped)
    -> [{"c": (x, y), "s": (w, h), "round", "fill"}] in points. Round = a closed ring of short strokes (found with or without a fill)."""
    out = []
    for d in page.get_drawings():
        r = d["rect"]
        if not (region[0] < r.x0 < region[2] and region[1] < r.y0 < region[3]) or not (lo < r.width < hi and lo < r.height < hi):
            continue
        if not (d.get("closePath") or d.get("fill") or len(d["items"]) > 6) or max(r.width, r.height) > 2.2 * min(r.width, r.height):
            continue
        if d.get("fill") and min(d["fill"]) > 0.95:
            continue
        c = ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
        if all(math.dist(c, q["c"]) > 2 for q in out):
            out.append({"c": c, "s": (r.width, r.height), "fill": bool(d.get("fill")), "round": False})
    # rings of short strokes = round outlines (a filled RC column, or an unfilled steel CHS)
    short = [a for a in rd.segments(page) if a[4] >= 0.9 and math.hypot(a[2] - a[0], a[3] - a[1]) < 0.12 * hi
             and region[0] < a[0] < region[2] and region[1] < a[1] < region[3]]
    par = list(range(len(short)))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    cell = {}
    for i, a in enumerate(short):
        for e in (a[:2], a[2:4]):
            for j in cell.setdefault((round(e[0] / 0.4), round(e[1] / 0.4)), []):
                par[find(i)] = find(j)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx or dy:
                        for j in cell.get((round(e[0] / 0.4) + dx, round(e[1] / 0.4) + dy), []):
                            par[find(i)] = find(j)
            cell[(round(e[0] / 0.4), round(e[1] / 0.4))].append(i)
    rings = {}
    for i, a in enumerate(short):
        rings.setdefault(find(i), []).extend([a[:2], a[2:4]])
    for pts in rings.values():
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        c = ((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2)
        if len(pts) < 24 or not (lo < w < hi) or abs(w - h) > 0.1 * w or max(abs(math.dist(p, c) - w / 2) for p in pts) > 0.1 * w:
            continue
        near = [q for q in out if math.dist(c, q["c"]) < 0.3 * w]
        if near:
            near[0].update({"round": True, "s": (w, w)})
        else:
            out.append({"c": c, "s": (w, w), "fill": False, "round": True})
    return out


def bands(lines, lo=5, hi=32, minlen=25):
    """Members drawn as outlines (elevations): parallel lines lo..hi pt apart that overlap by 60 % are one member.
    -> [{"a", "b" (centre line ends), "w" (outline width), "ang" (degrees), "n" (lines in the outline)}]."""
    L = [(m, math.hypot(m[2] - m[0], m[3] - m[1])) for m in lines]
    L = [(m, l) for m, l in L if l >= minlen]
    info = []
    for m, l in L:
        t = ((m[2] - m[0]) / l, (m[3] - m[1]) / l)
        if t[0] < 0 or (abs(t[0]) < 1e-9 and t[1] < 0):
            t = (-t[0], -t[1])
        info.append((t, -m[0] * t[1] + m[1] * t[0], sorted([m[0] * t[0] + m[1] * t[1], m[2] * t[0] + m[3] * t[1]]), l))
    par = list(range(len(L)))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    for i in range(len(L)):
        ti, oi, si, li = info[i]
        for j in range(i + 1, len(L)):
            if abs(ti[0] * info[j][0][1] - ti[1] * info[j][0][0]) > 0.02:
                continue
            m = L[j][0]
            oj = -m[0] * ti[1] + m[1] * ti[0]
            sj = sorted([m[0] * ti[0] + m[1] * ti[1], m[2] * ti[0] + m[3] * ti[1]])
            if lo <= abs(oj - oi) <= hi and min(si[1], sj[1]) - max(si[0], sj[0]) > 0.6 * min(li, info[j][3]):
                par[find(i)] = find(j)
    groups = {}
    for i in range(len(L)):
        groups.setdefault(find(i), []).append(i)
    out = []
    for ids in groups.values():
        if len(ids) < 2:
            continue
        t = info[ids[0]][0]
        offs = [-L[i][0][0] * t[1] + L[i][0][1] * t[0] for i in ids]
        ss = [v for i in ids for v in (L[i][0][0] * t[0] + L[i][0][1] * t[1], L[i][0][2] * t[0] + L[i][0][3] * t[1])]
        oc = (min(offs) + max(offs)) / 2
        P = lambda s_: (s_ * t[0] - oc * t[1], s_ * t[1] + oc * t[0])
        out.append({"a": P(min(ss)), "b": P(max(ss)), "w": max(offs) - min(offs), "ang": math.degrees(math.atan2(t[1], t[0])), "n": len(ids)})
    return out


# ---------------- framing: every end runs to its neighbour ----------------
def _dims(pf):
    """Depth and width of a section (I / RHS: h x b, SHS: b, CHS: d)."""
    return pf.get("h", pf.get("d", pf.get("b"))), pf.get("b", pf.get("d"))


def connect(beams, cols, profiles, lines=(), reach=REACH, back=BACK):
    """beams [{id, a, b (plan mm, as drawn), prof, arc, flat (web horizontal: bears, never coped)}], cols [{c, s, round}], lines [(x0, y0, x1, y1)] = drawn lines
    without a mark (RC wall edge, unmarked member), used only when an end finds no steel and no column.
    Sets a, b, ends, end_kind per beam (col | beam | host | butt | line | arc | free) and returns
    (cautions, ids of beams whose host stops short of the joint)."""
    S15, S3 = math.sin(math.radians(15)), math.sin(math.radians(3))
    root = {}

    def find(i):
        while root.setdefault(i, i) != i:
            root[i] = root[root[i]]
            i = root[i]
        return i
    key = lambda p: (round(p[0]), round(p[1]))
    joints = {}
    for bm in beams:
        a, b = bm["a"], bm["b"]
        L = math.dist(a, b)
        bm["_a"], bm["_b"], bm["_L"], bm["_t"] = list(a), list(b), L, ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        bm["_d"], bm["_w"] = _dims(profiles[bm["prof"]])[::-1 if bm.get("flat") else 1]      # flat = web horizontal
        bm["ends"], bm["end_kind"], bm["_at"] = [None, None], ["free", "free"], [None, None]
        if bm.get("arc"):
            for e in ("a", "b"):
                joints.setdefault(key(bm[e]), []).append(bm["id"])
    ends = [(bm, k) for bm in beams for k in (0, 1) if not (bm.get("arc") and len(joints[key(bm["ab"[k]])]) > 1)]
    E_ = lambda bm, k: bm["_a"] if k == 0 else bm["_b"]
    out_ = lambda bm, k: (-bm["_t"][0], -bm["_t"][1]) if k == 0 else bm["_t"]
    # 1. the beam in line with each end (same line within 150 mm, its nearer end ahead within 2 x reach)
    partner = {}
    for bm, k in ends:
        E, o, t = E_(bm, k), out_(bm, k), bm["_t"]
        best = None
        for h in beams:
            if h is bm or abs(t[0] * h["_t"][1] - t[1] * h["_t"][0]) > S3:
                continue
            if abs((h["_a"][0] - E[0]) * t[1] - (h["_a"][1] - E[1]) * t[0]) > 150:
                continue
            f = [(Q[0] - E[0]) * o[0] + (Q[1] - E[1]) * o[1] for Q in (h["_a"], h["_b"])]
            kh = 0 if f[0] < f[1] else 1
            if -back <= f[kh] <= 2 * reach and (best is None or f[kh] < best[2]):
                best = (h, kh, f[kh])
        if best:
            partner[(bm["id"], k)] = best
            root[find(bm["id"])] = find(best[0]["id"])
    nd = lambda bm, k: max(bm["_d"], partner[(bm["id"], k)][0]["_d"]) if (bm["id"], k) in partner else bm["_d"]
    prio = lambda bm, k: (nd(bm, k), find(bm["id"]))
    cautions = []
    # 2. each end picks its nearest neighbour
    for bm, k in ends:
        E, o, t, e = E_(bm, k), out_(bm, k), bm["_t"], "ab"[k]
        pt = partner.get((bm["id"], k))
        lim = pt[2] if pt else 1e9                        # nothing beyond the in-line beam's end counts
        col = None
        for c in cols:
            vx, vy = c["c"][0] - E[0], c["c"][1] - E[1]
            ahead, perp = vx * o[0] + vy * o[1], abs(vx * t[1] - vy * t[0])
            r = max(c["s"]) / 2
            if perp > max(r, 250) or not (-r - back <= ahead <= reach + r):
                continue
            if c.get("round"):
                half = math.sqrt(max(0.0, r * r - perp * perp))
            else:
                half = min(c["s"][0] / 2 / abs(o[0]) if abs(o[0]) > 1e-6 else 1e9, c["s"][1] / 2 / abs(o[1]) if abs(o[1]) > 1e-6 else 1e9)
            f = ahead - half
            if col is None or abs(f) < abs(col[0]):
                col = (f, c)
        crosses = []
        for h in beams:
            if h is bm:
                continue
            ht = h["_t"]
            cr = t[0] * ht[1] - t[1] * ht[0]
            if abs(cr) < S15:
                continue
            wx, wy = h["_a"][0] - bm["_a"][0], h["_a"][1] - bm["_a"][1]
            s_ = (wx * ht[1] - wy * ht[0]) / cr               # along bm from its drawn start
            u_ = (wx * t[1] - wy * t[0]) / cr                 # along h
            f = -s_ if k == 0 else s_ - bm["_L"]
            ext = max(0.0, -u_, u_ - h["_L"])                 # how far h's own line must run to get there
            if -back <= f <= min(reach, lim) and ext <= reach:
                crosses.append((abs(f) + ext, f, h, u_))
        cross = min(crosses, key=lambda c: c[0], default=None)
        if col and (cross is None or abs(col[0]) <= cross[0]) and col[0] <= lim:
            f, c = col
            bm[e] = [round(E[0] + o[0] * f, 1), round(E[1] + o[1] * f, 1)]
            bm["end_kind"][k] = "col"
            if bm["_w"] > min(c["s"]) + 25:
                cautions.append({"k": "wide", "bm": bm["id"], "col": c})
            continue
        if cross:
            # every line through this node (within 300 mm of the nearest crossing): the strongest one that runs
            # through or outranks this end is the host; if none does, this line is the one that runs through
            hosts = []
            for _, f, h, u_ in crosses:
                if abs(f - cross[1]) > 300:
                    continue
                kh = 0 if u_ < h["_L"] / 2 else 1
                hp = partner.get((h["id"], kh))
                if hp and max(-u_, u_ - h["_L"]) > hp[2] / 2:           # joint lies past the butt: the in-line beam hosts
                    P = (E[0] + o[0] * f, E[1] + o[1] * f)
                    h, kh = hp[0], hp[1]
                    u_ = (P[0] - h["_a"][0]) * h["_t"][0] + (P[1] - h["_a"][1]) * h["_t"][1]
                through = 300 < u_ < h["_L"] - 300
                if through or prio(h, kh) > prio(bm, k):
                    hosts.append(((through, prio(h, kh)), f, h, u_))
            if hosts:
                _, f, h, u_ = max(hosts, key=lambda c: c[0])
                bm[e] = [round(E[0] + o[0] * f, 1), round(E[1] + o[1] * f, 1)]
                both_i = profiles[h["prof"]]["type"] == "I" and profiles[bm["prof"]]["type"] == "I" and not (h.get("flat") or bm.get("flat"))
                bm["ends"][k] = [{"host": h["id"], "face": "cope" if both_i else "near"}]
                bm["end_kind"][k], bm["_at"][k] = "beam", (h, u_)
                if bm["_d"] > h["_d"] + 25:
                    cautions.append({"k": "deep", "bm": bm["id"], "on": h["id"]})
                continue
            if not pt:                                        # this line runs through: square end on the joint
                f = cross[1]
                bm[e] = [round(E[0] + o[0] * f, 1), round(E[1] + o[1] * f, 1)]
                bm["end_kind"][k] = "host"
                continue
        if pt:                                                # butt joint with the beam in line, at mid-gap
            h, kh, f = pt
            Q, oh = E_(h, kh), out_(h, kh)
            M = [(E[0] + Q[0]) / 2, (E[1] + Q[1]) / 2]
            n = (o[0] - oh[0], o[1] - oh[1])
            nl = math.hypot(*n)
            bm[e] = [round(M[0], 1), round(M[1], 1)]
            bm["ends"][k] = [{"plane": [n[0] / nl, n[1] / nl, 0, (n[0] * M[0] + n[1] * M[1]) / nl]}]
            bm["end_kind"][k] = "butt"
            if h["prof"] != bm["prof"] and bm["id"] < h["id"]:
                cautions.append({"k": "butt", "bm": bm["id"], "on": h["id"]})
            continue
        best = None                                           # last: a drawn line without a mark
        for q in lines:
            hL = math.dist(q[:2], q[2:])
            if hL < 300:
                continue
            ht = ((q[2] - q[0]) / hL, (q[3] - q[1]) / hL)
            cr = o[0] * ht[1] - o[1] * ht[0]
            if abs(cr) < S15:
                continue
            wx, wy = q[0] - E[0], q[1] - E[1]
            f, u_ = (wx * ht[1] - wy * ht[0]) / cr, (wx * o[1] - wy * o[0]) / cr
            if -back <= f <= reach and -300 <= u_ <= hL + 300 and (best is None or abs(f) < abs(best)):
                best = f
        if best is not None:
            bm[e] = [round(E[0] + o[0] * best, 1), round(E[1] + o[1] * best, 1)]
            bm["end_kind"][k] = "line"
    # 3. a host that stops short of a joint on its line runs on to it; what still misses is an open joint
    opened = []
    for bm in beams:
        for k in (0, 1):
            if not bm["_at"][k]:
                continue
            h, u_ = bm["_at"][k]
            ht = h["_t"]
            sa = (h["a"][0] - h["_a"][0]) * ht[0] + (h["a"][1] - h["_a"][1]) * ht[1]
            sb = (h["b"][0] - h["_a"][0]) * ht[0] + (h["b"][1] - h["_a"][1]) * ht[1]
            kh = 0 if u_ < sa - 20 else 1 if u_ > sb + 20 else None
            if kh is None or h["end_kind"][kh] == "butt":
                continue
            if h["end_kind"][kh] in ("free", "host"):
                h["ab"[kh]] = [round(h["_a"][0] + ht[0] * u_, 1), round(h["_a"][1] + ht[1] * u_, 1)]
                h["end_kind"][kh] = "host"
            else:
                opened.append(bm["id"])
    # 4. curved beams: chord joints mitred on the bisector plane (zero gap, no overlap)
    byid = {bm["id"]: bm for bm in beams}
    for J, ids in joints.items():
        if len(ids) < 2:
            continue
        for bm in (byid[i] for i in ids):
            bm["end_kind"][0 if key(bm["_a"]) == J else 1] = "arc"
        if len(ids) != 2:
            continue
        t = []
        for bm in (byid[ids[0]], byid[ids[1]]):                # direction pointing away from the joint
            o = bm["_b"] if key(bm["_a"]) == J else bm["_a"]
            L = math.dist(o, J)
            t.append(((o[0] - J[0]) / L, (o[1] - J[1]) / L))
        n = (t[0][0] - t[1][0], t[0][1] - t[1][1])
        nl = math.hypot(*n)
        if nl < 1e-6:
            continue
        n = (n[0] / nl, n[1] / nl)
        for bm in (byid[ids[0]], byid[ids[1]]):
            bm["ends"][0 if key(bm["_a"]) == J else 1] = [{"plane": [n[0], n[1], 0, n[0] * J[0] + n[1] * J[1]]}]
    for bm in beams:
        for kk in [kk for kk in bm if kk.startswith("_")]:
            del bm[kk]
    return cautions, opened


def bondek(fl, members, profiles, floor, tos, slab, span=4600, pitch=300):
    """Bondek package on one floor's beams `fl` (spec members): deck strip between neighbouring parallel beams up to
    `span` apart, edgeform on the outline of the deck union, one stud row per beam under the deck. Appends the
    members (mto measure rows, outside the steel kg) and returns {deck_m2, edgeform_m, studs}."""
    strips = []
    for m in fl:
        a, b = m["a"][:2], m["b"][:2]
        L = math.dist(a, b)
        t = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        n = (-t[1], t[0])
        best = None
        for o in fl:
            if o is m:
                continue
            oa, ob = o["a"][:2], o["b"][:2]
            oL = math.dist(oa, ob)
            ot = ((ob[0] - oa[0]) / oL, (ob[1] - oa[1]) / oL)
            if abs(t[0] * ot[1] - t[1] * ot[0]) > 0.02:
                continue
            off = (oa[0] - a[0]) * n[0] + (oa[1] - a[1]) * n[1]
            if not (200 < off < span):
                continue
            s0 = sorted([(oa[0] - a[0]) * t[0] + (oa[1] - a[1]) * t[1], (ob[0] - a[0]) * t[0] + (ob[1] - a[1]) * t[1]])
            lo, hi = max(0, s0[0]), min(L, s0[1])
            if hi - lo < 0.5 * min(L, oL):
                continue
            if best is None or off < best[0]:
                best = (off, lo, hi)
        if best:
            off, lo, hi = best
            P = lambda s_, w: (a[0] + s_ * t[0] + w * n[0], a[1] + s_ * t[1] + w * n[1])
            strips.append({"poly": [P(lo, 0), P(hi, 0), P(hi, off), P(lo, off)], "c": P((lo + hi) / 2, off / 2),
                           "len": hi - lo, "wid": off, "t": t})
    area = sum(s_["len"] * s_["wid"] for s_ in strips) / 1e6
    U = unary_union([Polygon(s_["poly"]).buffer(60, join_style=2) for s_ in strips]).buffer(-60, join_style=2) if strips else None
    rings = []
    if U is not None and not U.is_empty:
        for g in getattr(U, "geoms", [U]):
            g = g.simplify(20)
            rings += [list(g.exterior.coords)] + [list(r.coords) for r in g.interiors]
    common = {"ref": None, "rank": 9, "ends": [None, None], "floor": floor, "bldg": None, "tos": tos}
    for j, s_ in enumerate(strips):
        pn = f"BDK {round(s_['wid'])}"
        profiles.setdefault(pn, {"type": "PL", "b": round(s_["wid"], 1), "t": 1.0, "kgm": 0.0})
        c, t = s_["c"], s_["t"]
        members.append({**common, "id": f"{floor}-bdk{j}", "prof": pn, "layer": "bdk", "up": [0, 0, 1],
                        "a": [c[0] - t[0] * s_["len"] / 2, c[1] - t[1] * s_["len"] / 2, tos + 0.5],
                        "b": [c[0] + t[0] * s_["len"] / 2, c[1] + t[1] * s_["len"] / 2, tos + 0.5],
                        "src": f"Deck between beam lines (BDK slab {slab} on the plans); Bondek II 1.0 BMT ASSUMED",
                        "mto": {"kind": "measure", "uom": "m2", "cat": "Bondek", "desc": "Bondek II 1.0 BMT metal deck (ASSUMED)",
                                "len": round(s_["len"]), "wid": round(s_["wid"]), "assumed": ["desc"]}})
    ef_len = 0
    for r in rings:
        for p, q in zip(r, r[1:]):
            L = math.dist(p, q)
            if L < 50:
                continue
            ef_len += L
            members.append({**common, "id": f"{floor}-ef{len(members)}", "prof": f"EF 1.2x{slab}", "layer": "ef",
                            "a": [p[0], p[1], tos + slab / 2], "b": [q[0], q[1], tos + slab / 2],
                            "up": [(q[1] - p[1]) / L, -(q[0] - p[0]) / L, 0],
                            "src": f"Slab edge / opening of the deck outline; edgeform ASSUMED 1.2 BMT x {slab}",
                            "mto": {"kind": "measure", "uom": "m", "cat": "Edgeform", "desc": f"Edgeform 1.2 BMT x {slab} high (ASSUMED)",
                                    "len": round(L), "assumed": ["desc"]}})
    profiles.setdefault(f"EF 1.2x{slab}", {"type": "PL", "b": slab, "t": 1.2, "kgm": 0.0})
    profiles.setdefault("SS row 19x100", {"type": "PL", "b": 19, "t": 100, "kgm": 0.0})   # one row = one 19 x 100 strip
    nst = 0
    under = U.buffer(300) if U is not None and not U.is_empty else None
    for m in fl:
        L = math.dist(m["a"][:2], m["b"][:2])
        n = int(L // pitch)
        if n < 1 or under is None or LineString([m["a"][:2], m["b"][:2]]).intersection(under).length < 0.5 * L:
            continue                                  # studs only on beams under the deck
        nst += n
        members.append({**common, "id": m["id"] + "-ss", "prof": "SS row 19x100", "layer": "ss", "up": [0, 0, 1],
                        "a": [m["a"][0], m["a"][1], tos + 50], "b": [m["b"][0], m["b"][1], tos + 50], "bldg": m["bldg"],
                        "host_beam": m["id"], "src": f"Shear studs on beam under the bondek slab (ASSUMED 19x100 @{pitch} single row)",
                        "mto": {"kind": "measure", "uom": "pcs", "cat": "Stud", "desc": f"Shear stud 19 dia x 100 @{pitch} (ASSUMED)",
                                "len": 100, "set": n, "assumed": ["desc"]}})
    return {"deck_m2": round(area), "edgeform_m": round(ef_len / 1000), "studs": nst}
