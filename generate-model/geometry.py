#!/usr/bin/env python3
"""spec.json -> steel parts as convex prisms (SKILL.md section 2 rules).

    python geometry.py SPEC.json PARTS.json

Spec (what Claude writes after reading the drawings):
{
  "profiles": {"UC 152x152x23": {"type": "I", "h": 152.4, "b": 152.2, "tw": 5.8, "tf": 6.8, "kgm": 23.0}, ...},
      types: I (h b tw tf) | SHS (b t) | LIPC lipped channel open to +u (h b t lip) | PL flat (b t)
  "members": [{
      "id": "TC-N", "t": "X-UB42-TC", "prof": "UC 203x203x46",
      "a": [x, y, z], "b": [x, y, z],        work points in mm (centre line runs WP to WP)
      "up": [0, 0, 1],                        section depth direction (default: global Z, or X for vertical members)
      "rank": 1,                              lower rank = host; used by "auto" ends
      "ends": ["auto", [{"host": "VR-1", "face": "far"}]],
      ...any other keys (layer, unit, src, grid, ...) are copied to the part unchanged
  }]
}
End at a / b:
  null                square cut at the work point
  "auto"  (default)   bear on the "near" face of every lower-rank member whose centre line passes
                      within 1 mm of the work point (diagonal at a node -> chord + vertical = true notch)
  [cut, ...]          explicit: {"host": id, "face": "near"|"far"|"+u"|"-u"|"+v"|"-v"|"web"|"+w"|"-w"|"cope"} or
                      {"plane": [nx, ny, nz, d]} (plane n.x = d); the member keeps the side its body is on
                      add "only": "web" | "flanges" | [plate indices] to cut only some plates (copes);
                      "cope" on an I host (member depth parallel to the host's): the web is split at the host's
                      inner flange faces, the band between them runs to the host web, the rest stops at the
                      flange tips (true notch, no web inside a host flange);
                      plate order: I = +u flange, -u flange, web; SHS = +u, -u, +v, -v walls;
                      LIPC = base, +v side, +v lip, -v side, -v lip
Welded = zero gap: each section plate is clipped by every bearing plane (half-space clip, capped),
never by moving vertices, so a corner end comes out as a true notch.
"""
import json
import sys

import numpy as np

EPS = 1e-6
EXTEND = 3000.0      # mm past the work point before an end is clipped back
AUTO_TOL = 1.0       # mm: work point to host centre line for "auto" ends


# ---------------- section plates (u = depth direction, v = width), centred on the section box ----------------
def plates(pf):
    t = pf["type"]
    if t == "I":
        h, b, tw, tf = pf["h"], pf["b"], pf["tw"], pf["tf"]
        return [(h / 2 - tf, h / 2, -b / 2, b / 2), (-h / 2, -h / 2 + tf, -b / 2, b / 2),
                (-h / 2 + tf, h / 2 - tf, -tw / 2, tw / 2)]
    if t == "SHS":
        b, s = pf["b"], pf["t"]
        return [(b / 2 - s, b / 2, -b / 2, b / 2), (-b / 2, -b / 2 + s, -b / 2, b / 2),
                (-b / 2 + s, b / 2 - s, b / 2 - s, b / 2), (-b / 2 + s, b / 2 - s, -b / 2, -b / 2 + s)]
    if t == "LIPC":
        h, b, s, lip = pf["h"], pf["b"], pf["t"], pf["lip"]
        return [(-h / 2, -h / 2 + s, -b / 2, b / 2),
                (-h / 2 + s, h / 2, b / 2 - s, b / 2), (h / 2 - s, h / 2, b / 2 - s - lip, b / 2 - s),
                (-h / 2 + s, h / 2, -b / 2, -b / 2 + s), (h / 2 - s, h / 2, -b / 2 + s, -b / 2 + s + lip)]
    if t == "PL":
        return [(-pf["t"] / 2, pf["t"] / 2, -pf["b"] / 2, pf["b"] / 2)]
    raise ValueError(f"unknown profile type {t}")


def half_dims(pf):
    """Half depth (u) and half width (v) of the section envelope."""
    if pf["type"] == "SHS":
        return pf["b"] / 2, pf["b"] / 2
    if pf["type"] == "PL":
        return pf["t"] / 2, pf["b"] / 2
    return pf["h"] / 2, pf["b"] / 2


# ---------------- member frame ----------------
def frame(m):
    a, b = np.asarray(m["a"], float), np.asarray(m["b"], float)
    x = b - a
    L = np.linalg.norm(x)
    if L < EPS:
        raise ValueError(f"{m['id']}: zero-length member")
    x /= L
    up = np.asarray(m.get("up") or ([1.0, 0, 0] if abs(x[2]) > 0.9 else [0, 0, 1.0]), float)
    u = up - (up @ x) * x
    if np.linalg.norm(u) < 1e-3:
        raise ValueError(f"{m['id']}: 'up' is parallel to the member axis")
    u /= np.linalg.norm(u)
    return a, b, x, u, np.cross(x, u)


# ---------------- convex polyhedron clipping ----------------
def box(a, x, u, v, s0, s1, r):
    """Prism of one section plate r=(u0,u1,v0,v1) between s0 and s1 along x. Faces CCW seen from outside."""
    u0, u1, v0, v1 = r
    P = lambda s, uu, vv: a + s * x + uu * u + vv * v
    c = [P(s0, u0, v0), P(s0, u1, v0), P(s0, u1, v1), P(s0, u0, v1),
         P(s1, u0, v0), P(s1, u1, v0), P(s1, u1, v1), P(s1, u0, v1)]
    idx = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    faces = [[c[i] for i in f] for f in idx]
    # make every face outward (x, u, v may be a left-handed triad only if v was flipped by caller)
    ctr = np.mean(c, axis=0)
    out = []
    for f in faces:
        n = np.cross(f[1] - f[0], f[2] - f[0])
        out.append(f if n @ (np.mean(f, axis=0) - ctr) > 0 else f[::-1])
    return out


def clip(faces, n, d):
    """Keep n.x <= d. Returns the clipped convex polyhedron (faces) with a capping face, or [] if nothing left."""
    out, cap = [], []
    for poly in faces:
        new = []
        k = len(poly)
        for i in range(k):
            P, Q = poly[i], poly[(i + 1) % k]
            dp, dq = n @ P - d, n @ Q - d
            if dp <= EPS:
                new.append(P)
                if dp >= -EPS:
                    cap.append(P)
            if (dp < -EPS < EPS < dq) or (dq < -EPS < EPS < dp):
                X = P + (Q - P) * (dp / (dp - dq))
                new.append(X)
                cap.append(X)
        if len(new) >= 3:
            out.append(new)
    if not out:
        return []
    uniq = []
    for p in cap:
        if all(np.linalg.norm(p - q) > 1e-4 for q in uniq):
            uniq.append(p)
    if len(uniq) >= 3:
        c = np.mean(uniq, axis=0)
        e1 = uniq[0] - c
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(n, e1)       # CCW about +n (outward normal of the cap)
        uniq.sort(key=lambda p: np.arctan2((p - c) @ e2, (p - c) @ e1))
        out = [f for f in out if not all(abs(n @ p - d) <= 1e-4 for p in f)]  # drop old faces lying in the cap
        out.append(uniq)
    return out


# ---------------- end cuts ----------------
def dist_point_segment(p, a, b):
    ab = b - a
    t = np.clip((p - a) @ ab / (ab @ ab), 0, 1)
    return np.linalg.norm(p - (a + t * ab))


def keep_side(n, d, body):
    """Orient plane n.x = d so the member body point is on the kept side n.x <= d."""
    return (-n, -d) if n @ body > d else (n, d)


def host_plane(host, face, into):
    """Plane (n, d) of one face of the host section (u = depth, v = width).
    face: near | far | +u | -u | +v | -v (envelope), web | +w | -w (web faces of an I host)."""
    a, _, x, u, v = host["_f"]
    pf = host["_pf"]
    hu, hv = half_dims(pf)
    if face in ("web", "+w", "-w"):
        if pf["type"] != "I":
            raise ValueError(f"{host['id']}: web face asked on a {pf['type']} host")
        nrm = (v if v @ into >= 0 else -v) if face == "web" else (v if face == "+w" else -v)
        return nrm, nrm @ a + pf["tw"] / 2
    cands = [(u, hu, "+u"), (-u, hu, "-u"), (v, hv, "+v"), (-v, hv, "-v")]
    if face in ("near", "far"):
        near = max(cands, key=lambda c: c[0] @ into)       # outward normal pointing most toward the member body
        nrm = near[0] if face == "near" else -near[0]
        off = near[1]                                     # opposite faces share the same offset
    else:
        nrm, off = [(c[0], c[1]) for c in cands if c[2] == face][0]
    return nrm, nrm @ a + off                             # host centre line is a + s*x, nrm is perpendicular to x


def expand(c):
    """'cope' into an I host's web: flanges stop at the host flange tips, web runs to the host web face."""
    if c.get("face") != "cope":
        return [c]
    return [dict(c, face="near", only="flanges"), dict(c, face="web", only="web")]


def cope_band(m, host):
    """u-range of the member web that lies between the host's flanges (member u parallel to host u),
    or None. Outside it the web would run into a host flange, so it stops at the flange tips."""
    pf = host["_pf"]
    if pf["type"] != "I" or m["_pf"]["type"] != "I":
        return None
    a, _, _, u, _ = m["_f"]
    ha, _, _, hu, _ = host["_f"]
    k = u @ hu
    if abs(k) < 0.999:
        return None
    inner = pf["h"] / 2 - pf["tf"]
    lo, hi = sorted(((hu @ ha + s * inner) - hu @ a) / k for s in (-1, 1))
    return lo, hi


def end_cuts(m, which, by_id, members):
    spec = (m.get("ends") or ["auto", "auto"])[which]
    a, b, x, _, _ = m["_f"]
    end_pt, into = (a, x) if which == 0 else (b, -x)
    body = (a + b) / 2                                    # the member body is on the kept side of every cut
    if spec is None:
        return []
    if spec == "auto":
        rank = m.get("rank", 9)
        spec = [{"host": h["id"], "face": "near"} for h in members
                if h is not m and h.get("rank", 9) < rank
                and dist_point_segment(end_pt, h["_f"][0], h["_f"][1]) <= AUTO_TOL]
    planes = []
    for c0 in spec:
        band = cope_band(m, by_id[c0["host"]]) if c0.get("face") == "cope" else None
        near = keep_side(*host_plane(by_id[c0["host"]], "near", into), body) if band else None
        for c in expand(c0):
            if "plane" in c:
                n, d = np.asarray(c["plane"][:3], float), float(c["plane"][3])
            else:
                n, d = host_plane(by_id[c["host"]], c["face"], into)
            n, d = keep_side(n, d, body)
            only = c.get("only")
            if only == "web":
                only = [2]
            elif only == "flanges":
                only = [0, 1]
            # cope web: only the band between the host flanges runs to the host web, the rest stops at the flange tips
            split = (band, near) if band and c.get("face") == "web" else None
            planes.append((n, d, None if only is None else set(only), split))
    return planes


# ---------------- build ----------------
def split_u(r, ts):
    """Split plate rectangle r = (u0, u1, v0, v1) at the u values ts that fall inside it."""
    us = sorted({r[0], r[1]} | {t for t in ts if r[0] < t < r[1]})
    return [(p, q, r[2], r[3]) for p, q in zip(us, us[1:]) if q - p > EPS]


def build_member(m, by_id, members, profiles):
    pf = m["_pf"]
    a, b, x, u, v = m["_f"]
    L = np.linalg.norm(b - a)
    cuts = [end_cuts(m, 0, by_id, members), end_cuts(m, 1, by_id, members)]
    s0 = -EXTEND if cuts[0] else 0.0
    s1 = L + EXTEND if cuts[1] else L
    prisms = []
    for k, r in enumerate(plates(pf)):
        bands = [r]
        for *_, only, split in cuts[0] + cuts[1]:
            if split and (only is None or k in only):
                (lo, hi), _ = split
                bands = [nb for b in bands for nb in split_u(b, (lo, hi))]
        for br in bands:
            faces = box(a, x, u, v, s0, s1, br)
            for n, d, only, split in cuts[0] + cuts[1]:
                if only is not None and k not in only:
                    continue
                if split:
                    (lo, hi), near = split
                    if not (lo - EPS <= br[0] and br[1] <= hi + EPS):
                        n, d = near
                faces = clip(faces, n, d)
                if not faces:
                    break
            if faces:
                prisms.append(faces)
    V = np.array([p for pr in prisms for f in pr for p in f])
    s = V @ x
    cut_len = float(s.max() - s.min())
    part = {k: val for k, val in m.items() if not k.startswith("_") and k not in ("a", "b", "up", "ends", "rank", "id")}
    part.update({
        "ax": [round(float(c), 5) for c in x],
        "L": round(cut_len, 1),
        "kg": round(pf["kgm"] * cut_len / 1000.0, 2),
        "pr": [[[[round(float(c), 1) for c in p] for p in f] for f in pr] for pr in prisms],
    })
    part.setdefault("desc", m["prof"])
    part.setdefault("plate", None)
    return part


def build(spec):
    profiles, members = spec["profiles"], spec["members"]
    by_id = {}
    for m in members:
        if m["id"] in by_id:
            raise ValueError(f"duplicate member id {m['id']}")
        m["_pf"] = profiles[m["prof"]]
        m["_f"] = frame(m)
        by_id[m["id"]] = m
    for m in members:
        for e in (m.get("ends") or []):
            for c in (e if isinstance(e, list) else []):
                if "host" in c and c["host"] not in by_id:
                    raise ValueError(f"{m['id']}: unknown host {c['host']}")
    return [build_member(m, by_id, members, profiles) for m in members if not m.get("host_only")]


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    parts = build(spec)
    json.dump(parts, open(sys.argv[2], "w", encoding="utf-8"), separators=(",", ":"))
    print(f"{len(parts)} parts, {sum(p['kg'] for p in parts):,.1f} kg -> {sys.argv[2]}")
