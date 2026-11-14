#!/usr/bin/env python3
"""Check the MTO columns: painting m2, handrail m run + kg/m run, grating m2, bondek m2, edgeform m run.

    python tests/test_columns.py

Builds a 2-unit spec with build_mto.py, recalculates with LibreOffice and compares every figure
with the value worked out here by hand. Numbers in the spec are test values, not catalogue data.
"""
import json
import pathlib
import subprocess
import sys

import openpyxl

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_mto  # noqa: E402

OUT = ROOT / "tests" / "out"


def spec():
    steel = [{"kind": "length", "d": "203", "w": "203", "t": "46", "cat": "UC", "grade": "S275", "desc": "UC203x203x46",
              "mark": "UC1", "kgm": 46.1, "m2m": 1.19, "len": 6000, "qty": 4, "src": "test"},
             {"kind": "plate", "cat": "Plate", "grade": "S275", "desc": "PL20 base", "mark": "PLT1",
              "len": 400, "wid": 400, "thk": 20, "qty": 4, "src": "test"}]
    hr = [{"kind": "length", "d": "48.3", "w": "3.2", "cat": "CHS", "grade": "S275", "desc": "CHS48.3x3.2 post",
           "mark": "HR1", "kgm": 3.56, "m2m": 0.152, "len": 1100, "qty": 5, "src": "test"},
          {"kind": "length", "d": "48.3", "w": "3.2", "cat": "CHS", "grade": "S275", "desc": "CHS48.3x3.2 top rail",
           "mark": "HR2", "kgm": 3.56, "m2m": 0.152, "len": 6000, "qty": 1, "run": True, "src": "test"},
          {"kind": "length", "d": "48.3", "w": "3.2", "cat": "CHS", "grade": "S275", "desc": "CHS48.3x3.2 mid rail",
           "mark": "HR3", "kgm": 3.56, "m2m": 0.152, "len": 6000, "qty": 1, "src": "test"},
          {"kind": "length", "d": "100", "w": "6", "cat": "FL", "grade": "S275", "desc": "FL100x6 toe board",
           "mark": "HR4", "kgm": 4.71, "m2m": 0.212, "len": 6000, "qty": 1, "src": "test"}]
    grt = [{"kind": "area", "cat": "GRT", "grade": "HDG", "desc": "Grating 32x5 @ 30 (kg/m2)", "mark": "GRT1",
            "kgm": 39.5, "len": 6000, "wid": 1000, "qty": 2, "src": "test", "assumed": ["kgm"]}]
    bdk = [{"kind": "measure", "uom": "m2", "cat": "Deck", "grade": "G550", "desc": "Bondek II 1.0 BMT (m2)",
            "mark": "BDK1", "len": 6000, "wid": 3000, "qty": 2, "src": "test", "assumed": ["desc"]},
           {"kind": "measure", "uom": "pcs", "cat": "Stud", "grade": "-", "desc": "Shear stud 19x100 (pcs)",
            "mark": "SS1", "qty": 40, "src": "test"},
           {"kind": "measure", "uom": "m", "cat": "Edge", "grade": "G550", "desc": "Edgeform 1.2 BMT (m)",
            "mark": "EF1", "len": 18000, "qty": 1, "src": "test"}]
    cats = [{"code": "A", "title": "STEEL FRAME", "dwg": "T-1"}, {"code": "B", "title": "HANDRAIL", "dwg": "T-2"},
            {"code": "C", "title": "GRATING", "dwg": "T-3"}, {"code": "D", "title": "BONDEK PACKAGE", "dwg": "T-4"}]
    return {"header": {"client": "TEST", "project": "MTO columns test", "description": "-", "contractor": "Steel Hub", "date": "12-11-2026"},
            "currency": "RM", "unit_label": "unit", "grand_total_label": "2 UNITS", "allowance": 0, "categories": cats,
            "units": [{"name": "U1", "rows": {"A": steel, "B": hr, "C": grt, "D": bdk}},
                      {"name": "U2", "rows": {"A": steel, "B": hr}}],
            "assumptions": ["test"], "decisions": ["Grating weight: supplier figure or keep 39.5 kg/m2?"], "left_out": [],
            "cautions": ["UB1 (UB610) frames into the shallower UB2 (UB305) - 2 joints"]}


def expected():
    hr_kg = 3.56 * 1.1 * 5 + 3.56 * 6 * 2 + 4.71 * 6
    steel_kg = 46.1 * 6 * 4 + 0.4 * 0.4 * 20 * 7.85 * 4
    grt_kg = 39.5 * 6 * 1 * 2
    return {
        "U1": {"A": (steel_kg, 1.19 * 6 * 4 + 2 * 0.4 * 0.4 * 4, 0, 0), "B": (hr_kg, (0.152 * (1.1 * 5 + 12) + 0.212 * 6), 6, 0),
               "C": (grt_kg, 0, 0, 12), "D": (0, 0, 18, 36)},
        "hr_kgm": hr_kg / 6,
        "grand_kg": 2 * steel_kg + 2 * hr_kg + grt_kg,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    x = OUT / "cols.xlsx"
    build_mto.build(spec(), str(x))
    subprocess.run(["soffice", "--headless", "--convert-to", "xlsx", "--outdir", str(OUT / "calc"), str(x)],
                   check=True, capture_output=True, timeout=120)
    wb = openpyxl.load_workbook(OUT / "calc" / "cols.xlsx", data_only=True)
    errs = [(ws.title, c.coordinate, c.value) for ws in wb for row in ws.iter_rows() for c in row
            if isinstance(c.value, str) and c.value.startswith("#")]
    e = expected()
    ok = not errs
    print("formula errors:", errs or "none")
    u1 = wb["U1"]
    head = [u1.cell(7, c).value for c in range(1, 24)]
    print("unit header K..W:", head[10:])
    for r in range(8, u1.max_row + 1):
        lab = str(u1.cell(r, 9).value or "")
        if lab.startswith("Sub-Total"):
            code = lab.split()[-1]
            got = tuple(round(float(u1.cell(r, c).value or 0), 2) for c in (18, 19, 20, 21))
            want = tuple(round(v, 2) for v in e["U1"][code])
            kgm = u1.cell(r, 22).value
            good = all(abs(a - b) < 0.02 for a, b in zip(got, want))
            ok &= good
            print(f"  U1 Sub-Total {code}: kg/paint/run/area {got} expected {want} kg/m run {kgm!r} {'OK' if good else 'MISMATCH'}")
            if code == "B":
                good = kgm is not None and abs(kgm - e["hr_kgm"]) < 0.01
                ok &= good
                print(f"    handrail kg/m run {kgm:.3f} expected {e['hr_kgm']:.3f} {'OK' if good else 'MISMATCH'}")
            if code == "D":
                ok &= kgm in (None, "")
    s = wb["Summary "]
    hs = [s.cell(7, c).value for c in range(1, s.max_column + 1)]
    print("summary header:", hs)
    for r in range(8, s.max_row + 1):
        lab = str(s.cell(r, 2).value or "")
        if lab in ("HANDRAIL", "GRATING", "BONDEK PACKAGE") or lab.startswith("GRAND TOTAL - 2 UNITS (kg)"):
            print("  ", [s.cell(r, c).value for c in range(2, s.max_column + 1)])
        if lab.startswith("GRAND TOTAL - 2 UNITS (kg)"):
            g = s.cell(r, 5).value
            good = abs(g - e["grand_kg"]) < 0.5
            ok &= good
            print(f"  grand total {g:.1f} kg expected {e['grand_kg']:.1f} (bondek not in tonnage) {'OK' if good else 'MISMATCH'}")
    col_b = [str(s.cell(r, 2).value or "") for r in range(1, s.max_row + 1)]
    col_a = [str(s.cell(r, 1).value or "") for r in range(1, s.max_row + 1)]
    order = ["CAUTIOUS", "LEFT OUT OF THIS TAKE-OFF", "DECISIONS FOR YOU", "ASSUMPTIONS / ITEMS TO VERIFY"]      # Yang's order
    heads = [h for h in col_a if h in order]
    good = heads == order and "Nothing left out." in col_b
    ok &= good
    print("summary note sections:", heads, "| empty left-out reads 'Nothing left out.':", "Nothing left out." in col_b, "OK" if good else "MISMATCH")
    errs2 = only_what_exists()
    ok &= not errs2
    print("only what exists (steel-only spec):", errs2 or "OK")
    print("ALL OK" if ok else "FAILED")
    return 0 if ok else 1


def only_what_exists():
    """No handrail, grating or bondek rows anywhere: those categories and the Run / Area / kg/m run columns are not shown."""
    sp = spec()
    for u in sp["units"]:
        u["rows"] = {"A": u["rows"]["A"]}
    x = OUT / "steel_only.xlsx"
    build_mto.build(sp, str(x))
    wb = openpyxl.load_workbook(x)
    errs = []
    for ws in wb.worksheets:
        text = " ".join(str(c.value) for row in ws.iter_rows() for c in row if c.value is not None)
        for word in ("HANDRAIL", "GRATING", "BONDEK"):
            if word in text:
                errs.append(f"{ws.title}: {word} shown although no such rows exist")
    u1 = wb["U1"]
    for col in ("T", "U", "V"):
        if not u1.column_dimensions[col].hidden:
            errs.append(f"U1 column {col} visible although unused")
    if u1.cell(7, 23).value != "Dim source / basis":
        errs.append("Dim source / basis is no longer the last column")
    full = openpyxl.load_workbook(OUT / "cols.xlsx")
    if full and any(full["U1"].column_dimensions[c].hidden for c in ("T", "U", "V")):
        errs.append("full spec: a used quantity column is hidden")
    return errs


if __name__ == "__main__":
    sys.exit(main())
