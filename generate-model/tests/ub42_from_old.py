#!/usr/bin/env python3
"""Regression for geometry.py: rebuild UB42 from a spec reverse-engineered from the old model.

    python tests/ub42_from_old.py tests/fixtures/ub4.data.json [unit_index=0]

For every old part of the unit: centre line, section 'up' and section sizes are measured from its
prisms; each end cap plane is matched to the envelope face of the member it bears on (host + face),
or kept as an explicit plane when it bears on a plate / something with no section frame.
geometry.py then rebuilds the parts and every prism is compared vertex by vertex with the old one.
"""
import collections
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import geometry  # noqa: E402

TOL_N, TOL_D = 2e-3, 0.3


def newell(f):
    f = np.asarray(f)
    n = np.zeros(3)
    for i in range(len(f)):
        a, b = f[i], f[(i + 1) % len(f)]
        n += [(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])]
    return n / np.linalg.norm(n)


def section_of(p):
    """Measure type, sizes, frame and centre of an old part from its prisms. None if not a rolled section."""
    pr = [np.array([v for f in q for v in f]) for q in p["pr"]]
    x = np.asarray(p["ax"], float)
    x /= np.linalg.norm(x)
    cen = [q.mean(0) for q in pr]
    name = p["prof"]
    perp = lambda w: w - (w @ x) * x
    if name.startswith(("UC", "UB", "HN")) and len(pr) == 3:       # two flanges + web
        u = perp(cen[0] - cen[1]); u /= np.linalg.norm(u); v = np.cross(x, u)
        c = perp((cen[0] + cen[1]) / 2)
        ext = lambda q, w: float(np.ptp(q @ w))
        pf = {"type": "I", "h": round(ext(np.vstack(pr), u), 2), "b": round(ext(pr[0], v), 2),
              "tw": round(ext(pr[2], v), 2), "tf": round(ext(pr[0], u), 2)}
    elif name.startswith("SHS") and len(pr) == 4:
        u = perp(cen[0] - cen[1]); u /= np.linalg.norm(u); v = np.cross(x, u)
        c = perp((cen[0] + cen[1]) / 2)
        pf = {"type": "SHS", "b": round(float(np.ptp(np.vstack(pr) @ u)), 2), "t": round(float(np.ptp(pr[0] @ u)), 2)}
    elif name.startswith("STRUT") and len(pr) == 5:                # base, side, lip, side, lip
        u = perp((cen[2] + cen[4]) / 2 - cen[0]); u /= np.linalg.norm(u); v = np.cross(x, u)
        allv = np.vstack(pr)
        t = float(np.ptp(pr[0] @ u)); h = float(np.ptp(allv @ u))
        c = perp(cen[0]) + u * (h / 2 - t / 2)
        pf = {"type": "LIPC", "h": round(h, 2), "b": round(float(np.ptp(allv @ v)), 2), "t": round(t, 2),
              "lip": round(float(np.ptp(pr[2] @ v)), 2)}
    else:
        return None
    # oblique cuts turn plates into trapezoids and pull their centroids sideways: take the section
    # centre from the box of all vertices in (u, v) and u from the normal of the biggest flange face
    big = max(p["pr"][0], key=lambda f: np.linalg.norm(np.cross(np.subtract(f[1], f[0]), np.subtract(f[2], f[0]))))
    un = newell(big); un = perp(un); un /= np.linalg.norm(un)
    u = un if un @ u > 0 else -un
    v = np.cross(x, u)
    allv = np.vstack(pr)
    pu, pv = allv @ u, allv @ v
    if pf["type"] == "LIPC":
        c = u * (pu.min() + pf["h"] / 2) + v * (pv.min() + pv.max()) / 2
    else:
        c = u * (pu.min() + pu.max()) / 2 + v * (pv.min() + pv.max()) / 2
    s = allv @ x
    return {"pf": pf, "x": x, "u": u, "v": v, "c": c, "s0": float(s.min()), "s1": float(s.max())}


def plate_map(p, sec):
    """Old prism index -> geometry.plates() index, by nearest plate centre in the section plane."""
    ref = [((r[0] + r[1]) / 2, (r[2] + r[3]) / 2) for r in geometry.plates(sec["pf"])]
    out = []
    for q in p["pr"]:
        m = np.array([v for f in q for v in f]).mean(0) - sec["c"]
        uv = (m @ sec["u"], m @ sec["v"])
        out.append(min(range(len(ref)), key=lambda k: (ref[k][0] - uv[0]) ** 2 + (ref[k][1] - uv[1]) ** 2))
    return out


def end_planes(p, sec, which):
    """Distinct cap planes (n, d, {plates}) at one end (which=0: s0 end, 1: s1 end)."""
    x = sec["x"]
    mid = (sec["s0"] + sec["s1"]) / 2
    pm = plate_map(p, sec)
    out = []
    for k, q in enumerate(p["pr"]):
        for f in q:
            n = newell(f)
            if abs(n @ x) < 0.05:
                continue
            s = np.mean(np.asarray(f) @ x)
            if (s < mid) != (which == 0):
                continue
            d = float(n @ np.mean(f, axis=0))
            hit = [o for o in out if np.linalg.norm(n - o[0]) < TOL_N and abs(d - o[1]) < TOL_D]
            if hit:
                hit[0][2].add(pm[k])
            else:
                out.append((n, d, {pm[k]}))
    n_pl = len(geometry.plates(sec["pf"]))
    return [(n, d, None if len(ks) == n_pl else sorted(ks)) for n, d, ks in out]


def envelope_faces(sec):
    hu, hv = geometry.half_dims(sec["pf"])
    c, u, v = sec["c"], sec["u"], sec["v"]
    f = [("+u", u, u @ c + hu), ("-u", -u, -u @ c + hu), ("+v", v, v @ c + hv), ("-v", -v, -v @ c + hv)]
    if sec["pf"]["type"] == "I":
        tw = sec["pf"]["tw"] / 2
        f += [("+w", v, v @ c + tw), ("-w", -v, -v @ c + tw)]
    return f


def main(data_path, unit):
    d = json.load(open(data_path, encoding="utf-8"))
    parts = d["parts"]
    secs = [section_of(p) for p in parts]
    lo = np.array([np.min([v for q in p["pr"] for f in q for v in f], 0) for p in parts])
    hi = np.array([np.max([v for q in p["pr"] for f in q for v in f], 0) for p in parts])
    target = [i for i, p in enumerate(parts) if p["unit"] == unit]

    profiles, members, needed_hosts = {}, {}, set()
    stats = collections.Counter()
    for i in target:
        p, sec = parts[i], secs[i]
        if sec is None:
            stats["skipped (no rolled section)"] += 1
            continue
        profiles.setdefault(p["prof"], dict(sec["pf"], kgm=d["profs"][p["prof"]]["kgm"]))
        ends = []
        for which in (0, 1):
            cuts = []
            planes = end_planes(p, sec, which)
            for n, dd, only in planes:
                found = None
                end_s = sec["s0"] if which == 0 else sec["s1"]
                end_pt = sec["c"] + end_s * sec["x"]
                near = np.where(np.all(lo - 5 <= end_pt + 400, 1) & np.all(hi + 5 >= end_pt - 400, 1))[0]
                for j in near:
                    if j == i or secs[j] is None:
                        continue
                    for lab, nrm, off in envelope_faces(secs[j]):
                        if (np.linalg.norm(nrm - n) < TOL_N and abs(off - dd) < TOL_D) or \
                           (np.linalg.norm(nrm + n) < TOL_N and abs(off + dd) < TOL_D):
                            found = {"host": f"P{j}", "face": lab}
                            needed_hosts.add(j)
                            break
                    if found:
                        break
                if found and only is not None:
                    found["only"] = only; stats["  of which partial (cope)"] += 1
                if found:
                    cuts.append(found); stats["end cut -> host face"] += 1
                elif abs(n @ sec["x"]) > 0.999 and only is None and len(planes) == 1:
                    stats["square end (no host)"] += 1          # square cut: the work point is the end
                else:
                    cuts.append({"plane": [*map(float, n), dd], **({"only": only} if only is not None else {})})
                    stats["end cut -> explicit plane"] += 1
            ends.append(cuts or None)
        members[i] = {"id": f"P{i}", "t": p["t"], "prof": p["prof"],
                      "a": (sec["c"] + sec["s0"] * sec["x"]).tolist(), "b": (sec["c"] + sec["s1"] * sec["x"]).tolist(),
                      "up": sec["u"].tolist(), "ends": ends}
    for j in needed_hosts - set(members):
        sec = secs[j]
        profiles.setdefault(parts[j]["prof"], dict(sec["pf"], kgm=d["profs"][parts[j]["prof"]]["kgm"]))
        members[j] = {"id": f"P{j}", "t": parts[j]["t"], "prof": parts[j]["prof"], "host_only": True,
                      "a": (sec["c"] + sec["s0"] * sec["x"]).tolist(), "b": (sec["c"] + sec["s1"] * sec["x"]).tolist(),
                      "up": sec["u"].tolist(), "ends": [None, None]}
    spec = {"profiles": profiles, "members": list(members.values())}
    out_dir = pathlib.Path(__file__).resolve().parent / "out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "ub42.spec.json").write_text(json.dumps(spec, separators=(",", ":")), encoding="utf-8")

    new = {int(m["id"][1:]): part for m, part in
           zip([m for m in spec["members"] if not m.get("host_only")], geometry.build(spec))}

    # ---- compare ----
    worst, bad = [], []
    for i, q in new.items():
        p = parts[i]
        oc = [np.array([v for f in pr for v in f]) for pr in p["pr"]]
        nc = [np.array([v for f in pr for v in f]) for pr in q["pr"]]
        dev = 0.0 if len(oc) == len(nc) else 1e9
        for A in oc:
            B = min(nc, key=lambda B: np.linalg.norm(B.mean(0) - A.mean(0)))
            dAB = np.linalg.norm(A[:, None] - B[None], axis=2)
            dev = max(dev, dAB.min(1).max(), dAB.min(0).max())
        dL, dkg = abs(q["L"] - p["L"]), abs(q["kg"] - p["kg"])
        worst.append((dev, p["t"], i, dL, dkg))
        if dev > 0.5 or dL > 0.5 or dkg > 0.05:
            bad.append((dev, p["t"], i, p["L"], q["L"], p["kg"], q["kg"]))
    worst.sort(reverse=True)
    print(f"unit {unit} ({d['units'][unit]}): {len(target)} old parts, rebuilt {len(new)}, "
          f"host-only context members {len(needed_hosts - set(new))}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    spec_chars = len((out_dir / "ub42.spec.json").read_text())
    print(f"  spec size: {spec_chars:,} chars vs old prisms {len(json.dumps([parts[i] for i in target])):,} chars")
    old_kg = sum(parts[i]["kg"] for i in new); new_kg = sum(q["kg"] for q in new.values())
    print(f"  weight old {old_kg:,.2f} kg / new {new_kg:,.2f} kg")
    print(f"  max vertex deviation {worst[0][0]:.3f} mm ({worst[0][1]}), parts over 0.5 mm / L or kg off: {len(bad)}")
    for b in bad[:15]:
        print("   BAD dev=%.2f %s P%d L %.1f->%.1f kg %.2f->%.2f" % b)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 0))
