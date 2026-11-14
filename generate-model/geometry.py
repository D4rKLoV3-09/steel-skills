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
                      plate order: I = +u flange, -u flange, web; SHS = +u, -u, +v, -v walls;
                      LIPC = base, +v side, +v lip, -v side, -v lip
Bondek package: always the same three standard models, whatever the product, thickness or stud length (only the
quantity matters; the description carries the spec). Profiles "BONDEK", "SHEAR STUD" and "EDGEFORM" are built in:
  {"id": "D1", "t": "BDK1", "prof": "BONDEK", "a": [..], "b": [..], "wid": 3000, "desc": "Bondek II 1.0 BMT"}
        a -> b = centre line of the deck strip along the span, on top of steel; "wid" = covered width  (MTO: m2)
  {"id": "S1", "t": "SS1", "prof": "SHEAR STUD", "a": [..], "b": [..], "spacing": 300, "desc": "Shear stud 19x100"}
        a -> b = the beam's top-flange centre line; one stud part every "spacing" (default 300)       (MTO: pcs)
  {"id": "E1", "t": "EF1", "prof": "EDGEFORM", "a": [..], "b": [..], "desc": "Edgeform 1.2 BMT x 150"}
        a -> b = slab edge on top of steel                                                             (MTO: m)
"assumed": true marks the description as ASSUMED in the MTO. The "mto" override is filled in automatically.
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
    if t == "DECK":       # standard deck model: 2 mm pan + 30 x 55 ribs at 200 centres, sitting on the a-b line
        w = pf["b"]
        n = max(1, int(w // DECK_PITCH))
        ribs = [(-w / 2 + (w - (n - 1) * DECK_PITCH) / 2 + k * DECK_PITCH) for k in range(n)]
        return [(0.0, 2.0, -w / 2, w / 2)] + [(2.0, DECK_RIB_H, v - 15.0, v + 15.0) for v in ribs]
    if t == "EDGE":       # standard edgeform model: 150 upstand + 50 foot, 3 mm
        return [(0.0, EDGE_H, -1.5, 1.5), (0.0, 3.0, 1.5, 50.0)]
    raise ValueError(f"unknown profile type {t}")


DECK_PITCH, DECK_RIB_H, EDGE_H = 200.0, 55.0, 150.0
STUD = {"shank": 19.0, "head": 32.0, "head_t": 10.0, "len": 100.0}       # one model for every stud (19 x 100 mill cert)
STD_PROFILES = {"BONDEK": {"type": "DECK", "kgm": 0.0}, "SHEAR STUD": {"type": "STUD", "kgm": 0.0},
                "EDGEFORM": {"type": "EDGE", "kgm": 0.0}}
STD_MTO = {"DECK": ("m2", "Deck", "Bondek II 1.0 BMT"), "STUD": ("pcs", "Stud", "Shear stud 19x100"),
           "EDGE": ("m", "Edge", "Edgeform 1.2 BMT")}


def std_mto(m, pf):
    """Bondek package parts are counted (m2 / pcs / m), not weighed: fill the MTO override from the member."""
    uom, cat, default = STD_MTO[pf["type"]]
    desc = m.get("desc") or default
    mto = {"kind": "measure", "uom": uom, "cat": cat, "desc": f"{desc} ({uom})"}
    if pf["type"] == "DECK":
        mto["wid"] = m["wid"]
    if m.get("assumed"):
        mto["assumed"] = ["desc"]
    return dict(mto, **(m.get("mto") or {}))


def round_prism(p, z, e1, e2, s0, s1, r, n=12):
    """Round bar as an n-sided convex prism between s0 and s1 along z. Faces outward."""
    ring = [(np.cos(2 * np.pi * k / n) * e1 + np.sin(2 * np.pi * k / n) * e2) * r for k in range(n)]
    bot, top = [p + s0 * z + q for q in ring], [p + s1 * z + q for q in ring]
    faces = [bot[::-1], top] + [[bot[k], bot[(k + 1) % n], top[(k + 1) % n], top[k]] for k in range(n)]
    ctr = p + (s0 + s1) / 2 * z
    out = []
    for f in faces:
        nrm = np.cross(f[1] - f[0], f[2] - f[0])
        out.append(f if nrm @ (np.mean(f, axis=0) - ctr) > 0 else f[::-1])
    return out


def stud_parts(m):
    """One stud row -> one part per stud, each the standard stud (round shank + round head, as the sample), standing on the a-b line."""
    a, b = np.asarray(m["a"], float), np.asarray(m["b"], float)
    L = np.linalg.norm(b - a)
    sp = float(m.get("spacing", 300))
    n = max(1, int(L // sp))
    along = (b - a) / L if L > EPS else np.array([1.0, 0, 0])
    z = np.array([0, 0, 1.0])
    side = np.cross(z, along)
    side = side / np.linalg.norm(side) if np.linalg.norm(side) > 1e-3 else np.array([0, 1.0, 0])
    fwd = np.cross(side, z)
    base = {k: v for k, v in m.items() if not k.startswith("_") and k not in ("a", "b", "up", "ends", "rank", "id", "spacing", "assumed", "wid")}
    out = []
    for k in range(n):
        p = a + along * ((L - (n - 1) * sp) / 2 + k * sp)
        hs, hh = STUD["shank"] / 2, STUD["head"] / 2
        prisms = [round_prism(p, z, fwd, side, 0.0, STUD["len"] - STUD["head_t"], hs),
                  round_prism(p, z, fwd, side, STUD["len"] - STUD["head_t"], STUD["len"], hh)]
        part = dict(base)
        part.update({"ax": [0.0, 0.0, 1.0], "L": STUD["len"], "kg": 0.0,
                     "pr": [[[[round(float(c), 1) for c in q] for q in f] for f in pr] for pr in prisms]})
        part.setdefault("desc", "Shear stud 19x100")
        part.setdefault("plate", None)
        out.append(part)
    return out


def half_dims(pf):
    """Half depth (u) and half width (v) of the section envelope."""
    if pf["type"] == "SHS":
        return pf["b"] / 2, pf["b"] / 2
    if pf["type"] == "PL":
        return pf["t"] / 2, pf["b"] / 2
    if pf["type"] in STD_MTO:
        return DECK_RIB_H / 2, pf.get("b", 50.0) / 2
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
    for c in [e for c0 in spec for e in expand(c0)]:
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
        planes.append((n, d, None if only is None else set(only)))
    return planes


# ---------------- build ----------------
def build_member(m, by_id, members, profiles):
    pf = m["_pf"]
    a, b, x, u, v = m["_f"]
    L = np.linalg.norm(b - a)
    cuts = [end_cuts(m, 0, by_id, members), end_cuts(m, 1, by_id, members)]
    s0 = -EXTEND if cuts[0] else 0.0
    s1 = L + EXTEND if cuts[1] else L
    prisms = []
    for k, r in enumerate(plates(pf)):
        faces = box(a, x, u, v, s0, s1, r)
        for n, d, only in cuts[0] + cuts[1]:
            if only is not None and k not in only:
                continue
            faces = clip(faces, n, d)
            if not faces:
                break
        if faces:
            prisms.append(faces)
    V = np.array([p for pr in prisms for f in pr for p in f])
    s = V @ x
    cut_len = float(s.max() - s.min())
    part = {k: val for k, val in m.items() if not k.startswith("_") and k not in ("a", "b", "up", "ends", "rank", "id", "wid", "spacing", "assumed")}
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
    profiles, members = dict(STD_PROFILES, **spec.get("profiles", {})), spec["members"]
    by_id = {}
    for m in members:
        if m["id"] in by_id:
            raise ValueError(f"duplicate member id {m['id']}")
        pf = profiles[m["prof"]]
        if pf["type"] in STD_MTO:                      # bondek package: standard model, free end cuts, counted not weighed
            if pf["type"] == "DECK":
                pf = dict(pf, b=float(m["wid"]))
            m["mto"] = std_mto(m, pf)
            m.setdefault("ends", [None, None])
            m.setdefault("rank", 9)
        m["_pf"] = pf
        m["_f"] = frame(m)
        by_id[m["id"]] = m
    for m in members:
        for e in (m.get("ends") or []):
            for c in (e if isinstance(e, list) else []):
                if "host" in c and c["host"] not in by_id:
                    raise ValueError(f"{m['id']}: unknown host {c['host']}")
    parts = []
    for m in members:
        if m.get("host_only"):
            continue
        parts += stud_parts(m) if m["_pf"]["type"] == "STUD" else [build_member(m, by_id, members, profiles)]
    return parts


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    parts = build(spec)
    json.dump(parts, open(sys.argv[2], "w", encoding="utf-8"), separators=(",", ":"))
    print(f"{len(parts)} parts, {sum(p['kg'] for p in parts):,.1f} kg -> {sys.argv[2]}")
