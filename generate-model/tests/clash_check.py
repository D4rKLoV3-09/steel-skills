#!/usr/bin/env python3
"""Clash and gap check on the real prisms (SAT), SKILL.md section 3.

    python tests/clash_check.py PARTS_OR_DATA.json [SPEC.json] [--tol 0.5]

Penetration: every pair of convex prisms from different parts whose overlap on every separating axis
(face normals of both + edge x edge) exceeds tol mm. Reported per pair of parts with the depth.
Gap (needs the spec): every member end that names a host must touch it; the SAT separation between
the member and its host is a lower bound of the true gap, so a reported gap is a real one. A cut marked
"sep": true only keeps a member off something and is not checked.
Exit code 0 = no penetration over tol (gaps are reported, they do not fail the run).
"""
import itertools
import json
import sys

import numpy as np


def prisms(parts):
    out = []        # (part index, vertices (n,3), face normals, edges)
    for i, p in enumerate(parts):
        for pr in p["pr"]:
            V = np.array([v for f in pr for v in f], float)
            N, E = [], []
            for f in pr:
                f = np.array(f, float)
                n = np.cross(f[1] - f[0], f[2] - f[0])
                if np.linalg.norm(n) > 1e-9:
                    N.append(n / np.linalg.norm(n))
                for k in range(len(f)):
                    e = f[(k + 1) % len(f)] - f[k]
                    if np.linalg.norm(e) > 1e-6:
                        E.append(e / np.linalg.norm(e))
            out.append((i, np.unique(V.round(3), axis=0), dedup(N), dedup(E)))
    return out


def dedup(vs):
    keep = []
    for v in vs:
        if all(abs(abs(v @ k) - 1) > 1e-6 for k in keep):
            keep.append(v)
    return np.array(keep) if keep else np.zeros((0, 3))


def sat(A, B):
    """Signed SAT result: >0 = minimum overlap (penetration depth), <0 = separation lower bound."""
    axes = [A[2], B[2]]
    if len(A[3]) and len(B[3]):
        C = np.cross(A[3][:, None, :], B[3][None, :, :]).reshape(-1, 3)
        n = np.linalg.norm(C, axis=1)
        axes.append(C[n > 1e-6] / n[n > 1e-6, None])
    ax = np.vstack(axes)
    pa, pb = A[1] @ ax.T, B[1] @ ax.T
    ov = np.minimum(pa.max(0), pb.max(0)) - np.maximum(pa.min(0), pb.min(0))
    return float(ov.min())


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tol = float(sys.argv[sys.argv.index("--tol") + 1]) if "--tol" in sys.argv else 0.5
    d = json.load(open(args[0], encoding="utf-8"))
    parts = d["parts"] if isinstance(d, dict) else d
    pr = prisms(parts)
    lo = np.array([p[1].min(0) for p in pr]); hi = np.array([p[1].max(0) for p in pr])
    order = np.argsort(lo[:, 0])
    hits = {}
    active = []
    for k in order:                                   # sweep and prune on x
        active = [j for j in active if hi[j, 0] > lo[k, 0] + tol]
        for j in active:
            if pr[j][0] == pr[k][0] or np.any(lo[k] > hi[j] - tol) or np.any(lo[j] > hi[k] - tol):
                continue
            depth = sat(pr[j], pr[k])
            if depth > tol:
                key = tuple(sorted((pr[j][0], pr[k][0])))
                hits[key] = max(hits.get(key, 0), depth)
        active.append(k)
    name = lambda i: f"{parts[i].get('t')}{'/' + parts[i]['ref'] if parts[i].get('ref') else ''} @ {parts[i].get('grid', '')}"
    print(f"{len(parts)} parts, {len(pr)} prisms: {len(hits)} penetrating pairs over {tol} mm")
    for (a, b), dep in sorted(hits.items(), key=lambda kv: -kv[1])[:60]:
        print(f"  {dep:7.1f} mm  {name(a)}  x  {name(b)}")
    if len(args) > 1:                                 # host contact check
        spec = json.load(open(args[1], encoding="utf-8"))
        ms = [m for m in spec["members"] if not m.get("host_only")]
        idx = {m["id"]: i for i, m in enumerate(ms)}
        by_part = {}
        for p in pr:
            by_part.setdefault(p[0], []).append(p)
        gaps = []
        for i, m in enumerate(ms):
            for e in (m.get("ends") or []):
                for c in (e if isinstance(e, list) else []):
                    h = c.get("host")
                    if h is None or h not in idx or c.get("sep"):     # "sep": separation cut, no contact meant
                        continue
                    sep = max(sat(a, b) for a in by_part[i] for b in by_part[idx[h]])
                    if sep < -tol:
                        gaps.append((-sep, m["id"], h, c.get("face")))
        print(f"host contacts: {len(gaps)} member ends not touching their host (gap > {tol} mm)")
        for g in sorted(gaps, reverse=True)[:40]:
            print(f"  {g[0]:7.1f} mm  {g[1]} -> {g[2]} ({g[3]})")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
