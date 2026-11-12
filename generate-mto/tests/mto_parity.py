#!/usr/bin/env python3
"""Page export (port/mto_workbook.js inside a built model page) vs build_mto.py: same spec -> same
workbook, cell by cell. Run after any change to build_mto.py or the port.

    python tests/mto_parity.py PAGE.html          (a page built by generate-model/build_model.py)

Specs: the page's own mtoSpec(null) (whole model) and the MTO columns test spec (handrail, grating, bondek).
Compares value/formula, font, fill, number format, alignment, border, merges, column widths, print area.
Then recalculates both with LibreOffice and compares the computed values.
"""
import asyncio
import base64
import json
import os
import pathlib
import subprocess
import sys

import openpyxl
from playwright.async_api import async_playwright

MTO = pathlib.Path(__file__).resolve().parents[1]                 # generate-mto
ROOT = MTO.parent / "generate-model"                              # page side of the hand-over
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(MTO))
sys.path.insert(0, str(MTO / "tests"))
import build_mto  # noqa: E402
import test_columns  # noqa: E402
from regress import handler  # noqa: E402

OUT = ROOT / "tests" / "out" / "parity"


def rgb(c):
    return None if c is None or c.rgb is None or not isinstance(c.rgb, str) else c.rgb[-6:].upper()


def style(c):
    fo, fi, al, bo = c.font, c.fill, c.alignment, c.border
    fillc = rgb(fi.fgColor) if fi is not None and fi.fill_type == "solid" else None
    return (fo.name, float(fo.sz or 11), bool(fo.b), rgb(fo.color) or "000000", fo.u or None, fillc, c.number_format,
            al.horizontal, al.vertical, bool(al.wrap_text),
            tuple((getattr(bo, s).style if getattr(bo, s) is not None else None) for s in ("left", "right", "top", "bottom")))


def val(c):
    v = c.value
    if v in (None, ""):
        return None
    if isinstance(v, str) and v.startswith("="):
        return v[1:]
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def compare(py, js, label):
    a, b = openpyxl.load_workbook(py), openpyxl.load_workbook(js)
    diffs = []
    if a.sheetnames != b.sheetnames:
        return [f"sheet names {a.sheetnames} vs {b.sheetnames}"]
    for name in a.sheetnames:
        x, y = a[name], b[name]
        rows, cols = max(x.max_row, y.max_row), max(x.max_column, y.max_column)
        for r in range(1, rows + 1):
            for c in range(1, cols + 1):
                cx, cy = x.cell(r, c), y.cell(r, c)
                if val(cx) != val(cy):
                    diffs.append(f"{name}!{cx.coordinate} value {val(cx)!r} vs {val(cy)!r}")
                elif val(cx) is not None or style(cx)[5] or any(style(cx)[10]):
                    if style(cx) != style(cy):
                        diffs.append(f"{name}!{cx.coordinate} style {style(cx)} vs {style(cy)}")
        if sorted(map(str, x.merged_cells.ranges)) != sorted(map(str, y.merged_cells.ranges)):
            diffs.append(f"{name} merges differ")
        def widths(ws):
            w = {}
            for d in ws.column_dimensions.values():
                if d.customWidth:
                    for k in range(d.min or 0, (d.max or d.min or 0) + 1):
                        w[k] = d.width
            return w
        wx_, wy_ = widths(x), widths(y)
        for c in sorted(set(wx_) | set(wy_)):
            if abs((wx_.get(c) or 0) - (wy_.get(c) or 0)) > 0.01:
                diffs.append(f"{name} col {openpyxl.utils.get_column_letter(c)} width {wx_.get(c)} vs {wy_.get(c)}")
        px, py_ = str(x.print_area or ""), str(y.print_area or "")
        if px.replace("$", "") != py_.replace("$", ""):
            diffs.append(f"{name} print area {px} vs {py_}")
        if x.freeze_panes != y.freeze_panes:
            diffs.append(f"{name} freeze {x.freeze_panes} vs {y.freeze_panes}")
    return diffs


def recalc_values(path):
    out = path.parent / "calc"
    subprocess.run(["soffice", "--headless", "--convert-to", "xlsx", "--outdir", str(out), str(path)],
                   check=True, capture_output=True, timeout=180)
    wb = openpyxl.load_workbook(out / path.name, data_only=True)
    return {(ws.title, c.coordinate): c.value for ws in wb for row in ws.iter_rows() for c in row if c.value not in (None, "")}


async def page_books(html, specs):
    async with async_playwright() as pw:
        br = await pw.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = await br.new_page(viewport={"width": 1200, "height": 800})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        await page.route("**/*", handler)
        await page.goto("file://" + str(pathlib.Path(html).resolve()))
        await page.wait_for_function("window.__model && window.ExcelJS", timeout=240000)
        page_spec = await page.evaluate("() => JSON.parse(JSON.stringify(window.__model.mtoSpec(null)))")
        out = []
        for sp in [page_spec] + specs:
            b64 = await page.evaluate("""async (sp) => { const wb = buildWorkbook(sp); const buf = await wb.xlsx.writeBuffer();
                let s = ''; const u = new Uint8Array(buf); for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000));
                return btoa(s); }""", sp)
            out.append((sp, base64.b64decode(b64)))
        await br.close()
    return out, errs


def main(html):
    OUT.mkdir(parents=True, exist_ok=True)
    books, errs = asyncio.run(page_books(html, [test_columns.spec()]))
    ok = not errs
    if errs:
        print("page errors:", errs)
    for name, (sp, js_bytes) in zip(["model", "columns"], books):
        py, js = OUT / f"{name}_py.xlsx", OUT / f"{name}_js.xlsx"
        build_mto.build(json.loads(json.dumps(sp)), str(py))
        js.write_bytes(js_bytes)
        diffs = compare(py, js, name)
        va, vb = recalc_values(py), recalc_values(js)
        vd = [k for k in set(va) | set(vb) if not (va.get(k) == vb.get(k) or (isinstance(va.get(k), float) and isinstance(vb.get(k), float) and abs(va[k] - vb[k]) < 1e-6))]
        n_rows = sum(len(v) for u in sp["units"] for v in u["rows"].values())
        print(f"{name}: {len(sp['units'])} unit sheets, {n_rows} rows | cell/style differences: {len(diffs)} | computed-value differences: {len(vd)}")
        for d_ in diffs[:12]:
            print("   ", d_)
        for k in sorted(vd)[:8]:
            print("    value", k, va.get(k), "vs", vb.get(k))
        if name == "model":
            g = [v for (s, c), v in va.items() if s == "Summary " and isinstance(v, str) and v.startswith("GRAND TOTAL")]
            tot = [(c, v) for (s, c), v in va.items() if s == "Summary " and isinstance(v, (int, float))]
            print("    model Summary painted / grand totals:", [x for x in sorted(va.items()) if x[0][0] == "Summary " and str(x[1]).startswith("GRAND")][:2])
        ok &= not diffs and not vd
    print("PARITY OK" if ok else "PARITY FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
