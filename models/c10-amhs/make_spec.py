#!/usr/bin/env python3
"""C10 SAC AMHS bridge: drawings -> spec.json for geometry.py.

    python make_spec.py OUT_SPEC.json

Source: XXXX-LAY-LA1-00-SSTEL-001 Rev D (plan 1 TOS +21.850, plan 2 support level BOB +29.402,
legend, built-up section) and XXXX-SEC-LA1-00-SSTEL-001 Rev D (roof purlin plan, section 1-1,
typical bondek section). Positions read from the vector PDF (1:100, 35.273 mm/pt) and snapped to
the dimension chains; levels from the section (calibrated on FFL 22.200 / BOB 21.000 / TOC 20.732).

Axes: X along the bridge from grid LA1 (LA2 18000, LA3 49200, LA4 62700), Y north from grid LAB
(LAA 9600), Z absolute mm. West span LA1-LA2 is skewed in plan: its trusses run from
(710, 13800 / 4200) at LA1 to (17650, 9685 / 85) at LA2, as drawn.
Every member keeps its drawing mark in "ref"; make_data.py gives Yang's tags.

Rebuild (from the repo root; D = "jobs/C10 SAC Project/Models Data"):
    python models/c10-amhs/make_spec.py $D/c10-amhs.spec.json models/c10-amhs/purlin_marks.json
    python generate-model/geometry.py $D/c10-amhs.spec.json $D/c10-amhs.parts.json
    python models/c10-amhs/make_data.py $D/c10-amhs.spec.json $D/c10-amhs.parts.json $D/c10-amhs.data.json
    python generate-model/tests/clash_check.py $D/c10-amhs.data.json $D/c10-amhs.spec.json
    python generate-model/build_model.py $D/c10-amhs.data.json "jobs/C10 SAC Project/Models/C10_SAC_AMHS_Bridge.html"
purlin_marks.json = PR mark per (bay start x, row) read from the roof purlin plan labels.
"""
import json
import math
import sys

# ---------------- profiles (Consteel 2025 sizes; tw/tf from the EN10365 / BS4 tables) ----------------
I = lambda h, b, tw, tf, kgm: {"type": "I", "h": h, "b": b, "tw": tw, "tf": tf, "kgm": kgm}
P = {
    "UB 610x229x140": I(617.2, 230.2, 13.1, 22.1, 139.9),
    "UB 610x305x238": I(635.8, 311.4, 18.4, 31.4, 238.1),
    "UB 914x419x343": I(911.8, 418.5, 19.4, 32.0, 343.3),
    "UB 610x305x179": I(620.2, 307.1, 14.1, 23.6, 179.0),
    "UB 610x305x149": I(612.4, 304.8, 11.8, 19.7, 149.1),
    "UB 406x140x46": I(403.2, 142.2, 6.8, 11.2, 46.0),
    "UB 914x305x253": I(918.4, 305.5, 17.3, 27.9, 253.4),
    "UC 254x254x167": I(289.1, 265.2, 19.2, 31.7, 167.1),
    "UC 305x305x283": I(365.3, 322.2, 26.8, 44.1, 282.9),
    "UC 305x305x158": I(327.1, 311.2, 15.8, 25.0, 158.1),
    "UC 152x152x23": I(152.4, 152.2, 5.8, 6.8, 23.0),
    "BU 850x400x25x16": I(850.0, 400.0, 16.0, 25.0, 257.48),     # (2x400x25 + 800x16) mm2 x 7.85
    "SHS100x100x6.3": {"type": "SHS", "b": 100, "t": 6.3, "kgm": 18.4},
    "SHS180x180x6.3": {"type": "SHS", "b": 180, "t": 6.3, "kgm": 34.2},
    "C250x75x20x3.0": {"type": "LIPC", "h": 75, "b": 250, "t": 3.0, "lip": 20, "kgm": 9.89},
    "SS 19x100": {"type": "PL", "b": 19, "t": 19, "kgm": 2.23},        # stud shown as 19 mm square
    "EF 1.2x350": {"type": "PL", "b": 350, "t": 1.2, "kgm": 3.30},
}

# ---------------- grid, levels ----------------
LA = {"LA1": 0, "LA2": 18000, "LA3": 49200, "LA4": 62700}
TH = 4115 / 16940                              # west span skew: Y drop per mm of X
COS = math.cos(math.atan(TH))
Yt = lambda x: 13800 - (x - 710) * TH          # west north truss line
Yb = lambda x: Yt(x) - 9600                    # west south truss line
XW = [710 + i * 16940 / 9 for i in range(10)]  # west level-2 cross beams @1882
XM = [18300 + 1275 * i for i in range(25)]     # middle level-2 cross beams @1275
XE = [49550 + 13150 / 6 * i for i in range(7)] # east level-2 cross beams @2192
NW = [710, 710 + 16940 / 3, 710 + 2 * 16940 / 3, 17650]          # west truss nodes @5647
NM = [18300 + 5100 * i for i in range(7)]                        # middle truss nodes @5100
NE = [49550, 56125, 62700]                                       # east truss nodes @6575
XCANT = 63686                                  # east cantilever cross beam (1HSB09 / 2HSB06), LA4 + 986
XL2W, XL2E = 17650, 48900                       # span-end column lines at LA2 / LA3

TOS1, TOS3, TOC3 = 21850.0, 30109.0, 30320.0    # level-2 steel, level-3 beams, chord tops
COL_BOT = 20800.0                              # column underside on its base (TOC +20.732 + grout)
hh = lambda prof: P[prof]["h"] / 2


def zc(top, prof):
    return top - hh(prof)


members = []


def add(mid, ref, prof, a, b, rank, ends=None, up=None, **kw):
    m = {"id": mid, "ref": ref, "prof": prof, "a": [round(v, 2) for v in a], "b": [round(v, 2) for v in b], "rank": rank}
    if ends is not None:
        m["ends"] = ends
    if up is not None:
        m["up"] = up
    m.update(kw)
    members.append(m)
    return mid


def span_of(x):
    return "W" if x < LA["LA2"] else ("M" if x < LA["LA3"] else "E")


def grid_txt(x, y):
    g = max((k for k in LA if LA[k] <= x + 1), key=lambda k: LA[k])
    dx = x - LA[g]
    xs = g if abs(dx) < 1 else f"{g} {dx:+,.0f}"
    ys = "LAA" if abs(y - 9600) < 1 else ("LAB" if abs(y) < 1 else f"LAB {y:+,.0f}")
    return f"{xs} / {ys}"


SH1 = "LAY-001 plan 1 (TOS +21.850)"
SH2 = "LAY-001 plan 2 (support level, BOB +29.402)"
SHR = "SEC-001 roof purlin plan"
SHS = "SEC-001 section 1-1"

# ---------------- truss lines ----------------
# north (LAA) and south (LAB) truss line Y at x, per span
def ty(side, x):
    if x < LA["LA2"]:
        return Yt(x) if side == "N" else Yb(x)
    return 9600.0 if side == "N" else 0.0


SPANS = {  # chords, columns, verticals, levels
    "W": {"nodes": NW, "tc": "UB 610x305x179", "bc": "UB 610x305x179", "tref": "X-LB-TC-01", "bref": "X-LB-BC-01",
          "col": "UB 610x305x238", "cref": {"N": "X-LB-SC01", "S": "X-LB-SC02"}, "vr": {1: "X-LB-VR01", 2: "X-LB-VR01"}},
    "M": {"nodes": NM, "tc": "BU 850x400x25x16", "bc": "BU 850x400x25x16", "tref": "X-LB-TC-02", "bref": "X-LB-BC-02",
          "col": "UB 914x419x343", "cref": {"N": "X-LB-SC03", "S": "X-LB-SC04"},
          "vr": {1: "X-LB-VR02", 2: "X-LB-VR02", 3: "X-LB-VR03", 4: "X-LB-VR02", 5: "X-LB-VR02"}},
    "E": {"nodes": NE, "tc": "UB 610x305x179", "bc": "UB 610x305x179", "tref": "X-LB-TC-03", "bref": "X-LB-BC-03",
          "col": "UB 610x305x238", "cref": {"N": "X-LB-SC01", "S": "X-LB-SC02"}, "vr": {1: "X-LB-VR04"}},
}
VR_PROF = {"X-LB-VR01": "UC 254x254x167", "X-LB-VR02": "UC 305x305x283", "X-LB-VR03": "UC 305x305x283", "X-LB-VR04": "UC 254x254x167"}
DG_PROF = "UC 305x305x158"
# diagonals per span: (from node, 'T'/'B', to node, 'T'/'B', mark number); 'C' = panel centre (X brace)
DIAG = {
    "W": [(0, "T", 1, "B", 1), (1, "T", 2, "B", 2), (1, "B", "C", None, 3), ("C", None, 2, "T", 4), (2, "B", 3, "T", 1)],
    "M": [(0, "T", 1, "B", 5), (1, "T", 2, "B", 5), (2, "T", 3, "B", 6), (3, "B", 4, "T", 6), (4, "B", 5, "T", 5), (5, "B", 6, "T", 5)],
    "E": [(0, "T", 1, "B", 7), (1, "B", 2, "T", 7)],
}

col_at = {}     # (span, side, x) -> column id ; also lookup by x for beams
dg_top = {}     # (span, side, x) -> diagonals ending at that top-chord node
tc_id, bc_id, vr_id = {}, {}, {}
for sp, S in SPANS.items():
    nodes = S["nodes"]
    for side in "NS":
        ytr = lambda x: ty(side, x)
        trussplane_up = [TH, 1, 0] if sp == "W" else [0, 1, 0]     # section depth across the truss plane
        zb, zt = zc(TOS1, S["bc"]), zc(TOC3, S["tc"])
        lu = f"Truss {'LAA (north)' if side == 'N' else 'LAB (south)'} - {sp}"
        common = dict(span=sp, lu=lu, side=side)
        # end columns
        for x in (nodes[0], nodes[-1]):
            cid = add(f"COL-{sp}{side}-{x:.0f}", S["cref"][side], S["col"], [x, ytr(x), COL_BOT], [x, ytr(x), TOC3], 0, [None, None],
                      up=[0, 1, 0], layer="col", src=f"{SH1} / {SHS}; base on RC pier TOC +20.732", grid=grid_txt(x, ytr(x)), **common)
            col_at[(sp, side, round(x))] = cid
        # chords (one piece per span, column web to column web)
        x0, x1 = nodes[0], nodes[-1]
        c0, c1 = col_at[(sp, side, round(x0))], col_at[(sp, side, round(x1))]
        tc_id[(sp, side)] = add(f"TC-{sp}{side}", S["tref"], S["tc"], [x0, ytr(x0), zt], [x1, ytr(x1), zt], 1,
                                [[{"host": c0, "face": "web"}], [{"host": c1, "face": "web"}]], up=[0, 0, 1], layer="chord",
                                src=f"{SH2} / {SHS}; top +30.320 (section)", grid=grid_txt((x0 + x1) / 2, ytr((x0 + x1) / 2)), **common)
        bc_id[(sp, side)] = add(f"BC-{sp}{side}", S["bref"], S["bc"], [x0, ytr(x0), zb], [x1, ytr(x1), zb], 1,
                                [[{"host": c0, "face": "web"}], [{"host": c1, "face": "web"}]], up=[0, 0, 1], layer="chord",
                                src=f"{SH1} / {SHS}; top flush TOS +21.850", grid=grid_txt((x0 + x1) / 2, ytr((x0 + x1) / 2)), **common)
        # verticals
        for i, ref in S["vr"].items():
            x = nodes[i]
            vr_id[(sp, side, i)] = add(f"VR-{sp}{side}{i}", ref, VR_PROF[ref], [x, ytr(x), zb], [x, ytr(x), zt], 2, ["auto", "auto"],
                                       up=trussplane_up, layer="web", src=f"{SHS}; plan VR marks {SH1}", grid=grid_txt(x, ytr(x)), **common)
        # diagonals; south truss uses DG11-17 (legend), mirror of section 1-1
        def node_host(i, tb):
            x = nodes[i]
            chord = tc_id[(sp, side)] if tb == "T" else bc_id[(sp, side)]
            if i in (0, len(nodes) - 1):     # middle / east: the chord flange keeps the diagonal off the column web
                col = [{"host": col_at[(sp, side, round(x))], "face": "web"}] if sp == "W" else []
                return [x, ytr(x), zt if tb == "T" else zb], [{"host": chord, "face": "near"}] + col
            return [x, ytr(x), zt if tb == "T" else zb], [{"host": chord, "face": "near"}, {"host": vr_id[(sp, side, i)], "face": "near"}]
        cont = None
        for (i0, t0, i1, t1, n) in DIAG[sp]:
            mark = f"X-LB-DG{(n if side == 'N' else n + 10):02d}"
            if i0 == "C" or i1 == "C":
                xa, xb = nodes[1], nodes[2]
                xm = (xa + xb) / 2
                pc = [xm, ytr(xm), (zb + zt) / 2]
                if i0 == "C":
                    pb, eb = node_host(i1, t1)
                    a, b, ends = pc, pb, [[{"host": cont, "face": "near"}], eb]
                else:
                    pa, ea = node_host(i0, t0)
                    a, b, ends = pa, pc, [ea, [{"host": cont, "face": "near"}]]
                rank = 4
            else:
                a, ea = node_host(i0, t0)
                b, eb = node_host(i1, t1)
                ends, rank = [ea, eb], 3
            did = add(f"DG-{sp}{side}-{i0}{t0}-{i1}{t1}", mark, DG_PROF, a, b, rank, ends, up=trussplane_up, layer="web",
                      src=SHS + ("" if side == "N" else "; LAB truss not sectioned - mirror of 1-1 with DG11-17 (ASSUMED)"),
                      grid=grid_txt((a[0] + b[0]) / 2, ytr((a[0] + b[0]) / 2)), **common)
            if sp == "W" and i0 == 1 and i1 == 2:
                cont = did
            for i, t in ((i0, t0), (i1, t1)):
                if t == "T":
                    dg_top.setdefault((sp, side, round(nodes[i])), []).append(did)

# ---------------- level 2 floor (TOS +21.850): cross beams 1HSB, ties 1VSB, bracing 1BR ----------------
HSB1 = "UB 610x229x140"
z_h1 = zc(TOS1, HSB1)
OFFW = 2400 / COS                    # west 1VSB rows: 2400 square to the skewed chords
hsb1 = {}                            # x -> id


def l2_hsb(x, ref, src=SH1):
    sp = span_of(x)
    yN, yS = ty("N", x), ty("S", x)
    key = (sp, "N", round(x))
    if key in col_at:          # on a column line: bear on the column flanges
        ends, rank = [[{"host": col_at[(sp, "N", round(x))], "face": "near"}], [{"host": col_at[(sp, "S", round(x))], "face": "near"}]], 2
    else:
        ends, rank = [[{"host": bc_id[(sp, "N")], "face": "cope"}], [{"host": bc_id[(sp, "S")], "face": "cope"}]], 2
    hsb1[round(x)] = add(f"1HSB-{x:.0f}", ref, HSB1, [x, yN, z_h1], [x, yS, z_h1], rank, ends, up=[0, 0, 1], layer="l2",
                         span=sp, lu=None, src=src, grid=grid_txt(x, 4800), slab=True)


for i, x in enumerate(XW):
    l2_hsb(x, "X-LB-1HSB01" if i in (0, 9) else "X-LB-1HSB02")
for i, x in enumerate(XM):
    ref = "X-LB-1HSB03" if i in (0, 24) else ("X-LB-1HSB05" if x in (23400, 25950, 28500, 33600, 38700, 41250, 43800) else "X-LB-1HSB04")
    l2_hsb(x, ref)
for i, x in enumerate(XE):
    l2_hsb(x, "X-LB-1HSB06" if i in (0, 6) else ("X-LB-1HSB08" if i == 3 else "X-LB-1HSB07"))

VSB1 = "UC 152x152x23"
z_v1 = zc(TOS1, VSB1)
vsb1 = {}     # (bay x0, row) -> id


def l2_vsb(x0, x1, y0, y1, ref, row, prof=VSB1, z=z_v1, h0=None, h1=None):
    h0 = h0 or hsb1[round(x0)]
    h1 = h1 or hsb1[round(x1)]
    vid = add(f"1VSB-{x0:.0f}-{row}", ref, prof, [x0, y0, z], [x1, y1, z], 3,
              [[{"host": h0, "face": "cope"}], [{"host": h1, "face": "cope"}]], up=[0, 0, 1], layer="l2",
              span=span_of((x0 + x1) / 2), lu=None, src=SH1, grid=grid_txt((x0 + x1) / 2, (y0 + y1) / 2), slab=True)
    vsb1[(round(x0), row)] = vid
    return vid


for i in range(9):
    x0, x1 = XW[i], XW[i + 1]
    ref = "X-LB-1VSB01" if i in (0, 8) else "X-LB-1VSB02"
    l2_vsb(x0, x1, Yt(x0) - OFFW, Yt(x1) - OFFW, ref, "N")
    l2_vsb(x0, x1, Yb(x0) + OFFW, Yb(x1) + OFFW, ref, "S")
for row, y in (("N", 7200.0), ("S", 2400.0)):
    l2_vsb(XL2W, 18300, y, y, "X-LB-1VSB03", row)
    l2_vsb(48900, 49550, y, y, "X-LB-1VSB06", row)
    for i in range(24):
        l2_vsb(XM[i], XM[i + 1], y, y, "X-LB-1VSB04" if i in (0, 23) else "X-LB-1VSB05", row)
    for i in range(6):
        l2_vsb(XE[i], XE[i + 1], y, y, "X-LB-1VSB07" if i in (0, 5) else "X-LB-1VSB08", row)
# east cantilever: 1VSB10 (UB610) on the truss lines from the LA4 columns, 1HSB09 across, 1VSB09 ties
v10 = {}
for side, y in (("N", 9600.0), ("S", 0.0)):
    v10[side] = add(f"1VSB10-{side}", "X-LB-1VSB10", HSB1, [62700, y, z_h1], [XCANT, y, z_h1], 2,
                    [[{"host": col_at[("E", side, 62700)], "face": "web"}], None], up=[0, 0, 1], layer="l2",
                    span="E", lu=None, src=SH1 + "; cantilever past LA4", grid=grid_txt(63193, y), slab=True)
hsb1[XCANT] = add("1HSB09", "X-LB-1HSB09", HSB1, [XCANT, 9600, z_h1], [XCANT, 0, z_h1], 3,
                  [[{"host": v10["N"], "face": "cope"}], [{"host": v10["S"], "face": "cope"}]], up=[0, 0, 1], layer="l2",
                  span="E", lu=None, src=SH1, grid=grid_txt(XCANT, 4800), slab=True)
for row, y in (("N", 7200.0), ("S", 2400.0)):
    l2_vsb(62700, XCANT, y, y, "X-LB-1VSB09", row)

# 1BR plan bracing SHS100: chord node -> 1VSB node, every bay, pointing to mid-span (plan 1)
BR1 = "SHS100x100x6.3"
z_b1 = 21825.0 - 50.0                 # top under the 25 mm chord flange / beam top flanges


def br1(x_ch, y_ch, x_v, y_v, side, ref, bay_x0, src=SH1):
    sp = span_of((x_ch + x_v) / 2)
    hc = hsb1[round(x_ch)]
    if (sp, side, round(x_ch)) in col_at:   # the column fills the node: land in the column-flange / 1HSB-web corner
        e0 = [{"host": col_at[(sp, side, round(x_ch))], "face": "-u" if side == "N" else "+u"}, {"host": hc, "face": "web"}]
        y_ch += (-1 if side == "N" else 1) * hh(SPANS[sp]["col"])
    else:
        e0 = [{"host": bc_id[(sp, side)], "face": "web"}, {"host": hc, "face": "web"}]
    e1 = [{"host": vsb1[(round(bay_x0), side)], "face": "web"}, {"host": hsb1[round(x_v)], "face": "web"}]
    add(f"1BR-{x_ch:.0f}-{side}", ref, BR1, [x_ch, y_ch, z_b1], [x_v, y_v, z_b1], 5, [e0, e1], up=[0, 0, 1], layer="br",
        span=sp, lu=None, src=src, grid=grid_txt((x_ch + x_v) / 2, (y_ch + y_v) / 2))


for i in range(9):
    x0, x1 = XW[i], XW[i + 1]
    xc, xv = (x0, x1) if i <= 3 else (x1, x0)
    ref = "X-LB-1BR01" if i in (0, 8) else ("X-LB-1BR03" if i in (3, 5) else "X-LB-1BR02")
    br1(xc, Yt(xc), xv, Yt(xv) - OFFW, "N", ref, x0)
    br1(xc, Yb(xc), xv, Yb(xv) + OFFW, "S", ref, x0)
for i in range(24):
    x0, x1 = XM[i], XM[i + 1]
    xc, xv = (x0, x1) if i < 12 else (x1, x0)
    ref = "X-LB-1BR04" if i in (0, 23) else ("X-LB-1BR06" if xc in (23400, 28500, 38700, 43800) else "X-LB-1BR05")
    br1(xc, 9600, xv, 7200, "N", ref, x0)
    br1(xc, 0, xv, 2400, "S", ref, x0)
for i in range(6):
    x0, x1 = XE[i], XE[i + 1]
    xc, xv = (x0, x1) if i < 3 else (x1, x0)
    ref = "X-LB-1BR07" if i in (0, 5) else "X-LB-1BR08"
    br1(xc, 9600, xv, 7200, "N", ref, x0)
    br1(xc, 0, xv, 2400, "S", ref, x0)

# ---------------- level 3 support level: 2HSB (top +30.320), 2VSB (top +30.109) @1200, 2BR ----------------
hsb3 = {}


def l3_hsb(x, ref, prof):
    sp = span_of(x)
    z = zc(TOC3, prof)
    if (sp, "N", round(x)) in col_at:
        ends = [[{"host": col_at[(sp, "N", round(x))], "face": "near"}], [{"host": col_at[(sp, "S", round(x))], "face": "near"}]]
    else:
        ends = [[{"host": tc_id[(sp, "N")], "face": "cope"}], [{"host": tc_id[(sp, "S")], "face": "cope"}]]
    hsb3[round(x)] = add(f"2HSB-{x:.0f}", ref, prof, [x, ty("N", x), z], [x, ty("S", x), z], 2, ends, up=[0, 0, 1], layer="l3",
                         span=sp, lu=None, src=SH2 + "; top +30.320 (section 1-1)", grid=grid_txt(x, 4800))


for x in NW:
    l3_hsb(x, "X-LB-2HSB01" if x in (710, 17650) else "X-LB-2HSB02", "UB 610x305x179")
for x in NM:
    l3_hsb(x, "X-LB-2HSB03" if x in (18300, 48900) else "X-LB-2HSB04", "UB 610x305x149")
for x in NE:
    l3_hsb(x, "X-LB-2HSB05", "UB 610x305x179")
VSB3 = "UB 406x140x46"
z_v3 = zc(TOS3, VSB3)
v9 = {}
for side, y in (("N", 9600.0), ("S", 0.0)):
    v9[side] = add(f"2VSB09-{side}", "X-LB-2VSB09", "UB 914x305x253", [62700, y, zc(TOC3, "UB 914x305x253")],
                   [XCANT, y, zc(TOC3, "UB 914x305x253")], 2, [[{"host": col_at[("E", side, 62700)], "face": "web"}], None],
                   up=[0, 0, 1], layer="l3", span="E", lu=None, src=SH2 + "; cantilever past LA4, bottom = BOB +29.402", grid=grid_txt(63193, y))
z6 = zc(TOC3, "UB 610x305x179")
hsb3[XCANT] = add("2HSB06", "X-LB-2HSB06", "UB 610x305x179", [XCANT, 9600, z6], [XCANT, 0, z6], 3,
                  [[{"host": v9["N"], "face": "cope"}], [{"host": v9["S"], "face": "cope"}]], up=[0, 0, 1], layer="l3",
                  span="E", lu=None, src=SH2, grid=grid_txt(XCANT, 4800))


def l3_vsb(x0, x1, y0, y1, ref, k):
    add(f"2VSB-{x0:.0f}-{k}", ref, VSB3, [x0, y0, z_v3], [x1, y1, z_v3], 3,
        [[{"host": hsb3[round(x0)], "face": "cope"}], [{"host": hsb3[round(x1)], "face": "cope"}]], up=[0, 0, 1], layer="l3",
        span=span_of((x0 + x1) / 2), lu=None, src=SH2 + "; top TOS +30.109 (TYP.)", grid=grid_txt((x0 + x1) / 2, (y0 + y1) / 2))


for b in range(3):
    x0, x1 = NW[b], NW[b + 1]
    for k in range(1, 8):
        off = 4800 + (k - 4) * 1200 / COS       # 7 rows @1200 square to the skewed chords
        l3_vsb(x0, x1, Yt(x0) - off, Yt(x1) - off, "X-LB-2VSB02" if b == 1 else "X-LB-2VSB01", k)
for k in range(1, 8):
    y = 9600 - 1200 * k
    l3_vsb(XL2W, 18300, y, y, "X-LB-2VSB03", k)
    l3_vsb(48900, 49550, y, y, "X-LB-2VSB06", k)
    for b in range(6):
        l3_vsb(NM[b], NM[b + 1], y, y, "X-LB-2VSB04" if b in (0, 5) else "X-LB-2VSB05", k)
    for b in range(2):
        l3_vsb(NE[b], NE[b + 1], y, y, "X-LB-2VSB07", k)
    l3_vsb(62700, XCANT, y, y, "X-LB-2VSB08", k)

# 2BR SHS180 X-bracing under the level-3 beams (top +29.700): one continuous diagonal NW-SE + two halves
BR3 = "SHS180x180x6.3"
z_b3 = 29700.0 - 90.0


def br3_end(sp, side, x):
    if (sp, side, round(x)) in col_at:
        return [{"host": col_at[(sp, side, round(x))], "face": "near"}]
    # "sep": a cut that only keeps the brace off something (no contact expected; clash_check skips it)
    if sp == "M":       # into the TC-02 web; the 2HSB web plane parts the two braces meeting at the node
        return [{"host": tc_id[(sp, side)], "face": "web"}, {"host": hsb3[round(x)], "face": "web", "sep": True}]
    # under TC-01 / TC-03 and the 2HSB bottom flange; the diagonal heads (327 deep) stand 10 mm past the chord flange tips
    return ([{"host": tc_id[(sp, side)], "face": "near", "sep": True}, {"host": hsb3[round(x)], "face": "web"}]
            + [{"host": d, "face": "near", "sep": True} for d in dg_top.get((sp, side, round(x)), [])])


BR3MARK = {"W": [("01", "02", "03"), ("04", "05", "06"), ("01", "02", "03")],
           "M": [("07", "08", "09")] + [("10", "11", "12")] * 4 + [("07", "09", "08")],
           "E": [("13", "14", "15"), ("13", "15", "14")]}
for sp, nodes in (("W", NW), ("M", NM), ("E", NE)):
    for b in range(len(nodes) - 1):
        x0, x1 = nodes[b], nodes[b + 1]
        xm = (x0 + x1) / 2
        pc = [xm, (ty("N", xm) + ty("S", xm)) / 2, z_b3]
        mc, mne, msw = BR3MARK[sp][b]
        cid = add(f"2BR-{sp}{b}-C", f"X-LB-2BR{mc}", BR3, [x0, ty("N", x0), z_b3], [x1, ty("S", x1), z_b3], 5,
                  [br3_end(sp, "N", x0), br3_end(sp, "S", x1)], up=[0, 0, 1], layer="br", span=sp, lu=None, src=SH2,
                  grid=grid_txt(xm, 4800))
        add(f"2BR-{sp}{b}-NE", f"X-LB-2BR{mne}", BR3, [x1, ty("N", x1), z_b3], pc, 6, [br3_end(sp, "N", x1), [{"host": cid, "face": "near"}]],
            up=[0, 0, 1], layer="br", span=sp, lu=None, src=SH2, grid=grid_txt(xm, 4800))
        add(f"2BR-{sp}{b}-SW", f"X-LB-2BR{msw}", BR3, [x0, ty("S", x0), z_b3], pc, 6, [br3_end(sp, "S", x0), [{"host": cid, "face": "near"}]],
            up=[0, 0, 1], layer="br", span=sp, lu=None, src=SH2, grid=grid_txt(xm, 4800))

# ---------------- roof purlins C250 (underside +30.608 per section 1-1) ----------------
PRZ = 30608.0 + 125.0
ROWS = [9600, 8400, 7200, 6000, 4800, 3600, 2400, 1200, 725, 0]         # from LAA: 7 x 1200, 475, 725 (roof plan)
purlin_marks = json.load(open(sys.argv[2], encoding="utf-8")) if len(sys.argv) > 2 else {}
XR = sorted(set([round(x) for x in NW] + [round(x) for x in NM] + [round(x) for x in NE] + [XCANT]))
for b in range(len(XR) - 1):
    x0, x1 = XR[b], XR[b + 1]
    if (x0, x1) in ((17650, 18300), (48900, 49550)):
        continue                      # roof plan: purlin rows stop at the span joints LA2 / LA3
    bay = [purlin_marks[k] for k in purlin_marks if k.startswith(f"{x0}-")]
    bay_mark = max(set(bay), key=bay.count) if bay else "X-LB-PR05"   # unlabelled row: the bay's usual mark
    for r, off in enumerate(ROWS):
        if x1 <= 17650:
            y0, y1 = Yt(x0) - (9600 - off), Yt(x1) - (9600 - off)
        else:
            y0 = y1 = float(off)
        key = f"{x0}-{r}"
        add(f"PR-{key}", purlin_marks.get(key, bay_mark), "C250x75x20x3.0", [x0, y0, PRZ], [x1, y1, PRZ], 7, [None, None],
            up=[0, -1, 0] if off > 4800 else [0, 1, 0], layer="pr", span=span_of((x0 + x1) / 2), lu=None,
            src=SHR + " (C250x75x20x3.0 @1200, roof per section 1-1); purlin seat above beam not detailed",
            grid=grid_txt((x0 + x1) / 2, (y0 + y1) / 2))

# ---------------- bondek package on level 2 (Yang's scope; studs / deck / edgeform ASSUMED) ----------------
ZD = TOS1 + 0.5
EDGE_W, EDGE_E = 710 - 115.1, XCANT + 115.1
deck = [  # (id, x0, x1, y centre at x0, y centre at x1, square width, vertical width)
    ("BDK-W", EDGE_W, XL2W, Yt(EDGE_W) - 4800, Yt(XL2W) - 4800, (9600 + 2 * 153.55 / COS) * COS, 9600 + 2 * 153.55 / COS),
    ("BDK-M", XL2W, 48900, 4800, 4800, 10000, 10000),
    ("BDK-E", 48900, EDGE_E, 4800, 4800, 9600 + 307.1, 9600 + 307.1),
]
for did, x0, x1, ya, yb, wsq, wv in deck:
    pname = f"BDK {did[-1]}"
    P[pname] = {"type": "PL", "b": round(wsq, 1), "t": 1.0, "kgm": 0.0}
    xa, xb = x0 - 50, x1 + 50
    sl = (yb - ya) / (x1 - x0)
    add(did, None, pname, [xa, ya - sl * 50, ZD], [xb, yb + sl * 50, ZD], 9,
        [[{"plane": [1, 0, 0, x0]}], [{"plane": [1, 0, 0, x1]}]], up=[0, 0, 1], layer="bdk", span=span_of((x0 + x1) / 2), lu=None,
        src=SH1 + " BONDEK SLAB 350 THK; deck spec not on drawings (ASSUMED Bondek II 1.0 BMT)", grid=grid_txt((x0 + x1) / 2, 4800),
        mto={"kind": "measure", "uom": "m2", "cat": "Bondek", "desc": "Bondek II 1.0 BMT metal deck (ASSUMED)",
             "len": round(x1 - x0), "wid": round(wv), "assumed": ["desc"]})
EFZ = TOS1 + 175
ef = [("EF-WN", EDGE_W, XL2W, lambda x: Yt(x) + 153.55 / COS + 0.6), ("EF-WS", EDGE_W, XL2W, lambda x: Yb(x) - 153.55 / COS - 0.6),
      ("EF-MN", XL2W, 48900, lambda x: 9800.6), ("EF-MS", XL2W, 48900, lambda x: -200.6),
      ("EF-EN", 48900, EDGE_E, lambda x: 9754.2), ("EF-ES", 48900, EDGE_E, lambda x: -154.2)]
for eid, x0, x1, fy in ef:
    a, b = [x0, fy(x0), EFZ], [x1, fy(x1), EFZ]
    L = math.dist(a, b)
    add(eid, None, "EF 1.2x350", a, b, 9, [None, None], up=[-(b[1] - a[1]) / L, (b[0] - a[0]) / L, 0], layer="ef", span=span_of((x0 + x1) / 2),
        lu=None, src="Slab edge (350 THK, plan 1); edgeform ASSUMED 1.2 BMT x 350", grid=grid_txt((x0 + x1) / 2, fy((x0 + x1) / 2)),
        mto={"kind": "measure", "uom": "m", "cat": "Edgeform", "desc": "Edgeform 1.2 BMT x 350 high (ASSUMED)", "len": round(L), "assumed": ["desc"]})
for eid, x, y0, y1 in (("EF-W", EDGE_W - 0.6, Yb(EDGE_W) - 153.55 / COS, Yt(EDGE_W) + 153.55 / COS), ("EF-E", EDGE_E + 0.6, -153.55, 9753.55)):
    add(eid, None, "EF 1.2x350", [x, y0, EFZ], [x, y1, EFZ], 9, [None, None], up=[1, 0, 0], layer="ef", span=span_of(x), lu=None,
        src="Slab end (plan 1); edgeform ASSUMED 1.2 BMT x 350", grid=grid_txt(x, 4800),
        mto={"kind": "measure", "uom": "m", "cat": "Edgeform", "desc": "Edgeform 1.2 BMT x 350 high (ASSUMED)", "len": round(y1 - y0), "assumed": ["desc"]})
# shear studs 19x100 @300 single row on every beam under the slab (HSB, VSB, bottom chords)
beams = [m for m in members if m.get("slab")] + [m for m in members if m["id"].startswith("BC-")]
for m in list(beams):
    a, b = m["a"], m["b"]
    L = math.dist(a[:2], b[:2])
    top = TOS1
    n = int((L - 300) // 300) + 1
    s0 = (L - (n - 1) * 300) / 2
    for k in range(n):
        t = (s0 + 300 * k) / L
        x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        add(f"SS-{m['id']}-{k}", None, "SS 19x100", [x, y, top], [x, y, top + 100], 9, [None, None], up=[1, 0, 0], layer="ss",
            span=m["span"], lu=m["lu"], host_beam=m["id"], src="Shear stud on beam under the bondek slab (ASSUMED 19x100 @300)",
            grid=grid_txt(x, y), mto={"kind": "measure", "uom": "pcs", "cat": "Stud", "desc": "Shear stud 19 dia x 100 (ASSUMED)",
                                       "len": 100, "assumed": ["desc"]})

for m in members:
    m.pop("slab", None)
json.dump({"profiles": P, "members": members}, open(sys.argv[1], "w", encoding="utf-8"), indent=0)
print(f"{len(members)} members -> {sys.argv[1]}")
