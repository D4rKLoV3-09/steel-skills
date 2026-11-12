#!/usr/bin/env python3
"""Check the standing rules in a real browser on UB4 + a test handrail on the UB42 north top chord.

    python tests/rules_check.py

 1. selecting the handrail assembly shows kg/m run (= assembly kg / top-rail run)
 3. search finds a member by Yang tag and by a segment of its original (ref) tag
Test-only sizes: SHS50x50x3.0 4.25 kg/m and FL100x6 4.71 kg/m (fixture, not a model).
"""
import asyncio
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import geometry  # noqa: E402
from regress import handler  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

OUT = ROOT / "tests" / "out"


def fixture():
    d = json.loads((ROOT / "tests/fixtures/ub4.data.json").read_text(encoding="utf-8"))
    tc = next(p for p in d["parts"] if p["t"] == "X-UB42-TC" and min(v[1] for f in p["pr"][0] for v in f) > -2000)
    lu, tw = tc["lu"], tc["tw"]
    y, z0 = -1860.6, 20850.0
    xs = [-15000.0, -13500.0, -12000.0, -10500.0]
    prof = {"SHS50x50x3.0": {"type": "SHS", "b": 50, "t": 3, "kgm": 4.25},
            "FL100x6": {"type": "PL", "b": 100, "t": 6, "kgm": 4.71}}
    mem = [{"id": f"post{k}", "t": "HR1", "prof": "SHS50x50x3.0", "a": [x, y, z0], "b": [x, y, z0 + 1100],
            "up": [1, 0, 0], "ends": [None, None]} for k, x in enumerate(xs)]
    mem += [{"id": "top", "t": "HR2", "rail": "top", "prof": "SHS50x50x3.0", "a": [xs[0] - 25, y, z0 + 1125],
             "b": [xs[-1] + 25, y, z0 + 1125], "ends": [None, None]},
            {"id": "mid", "t": "HR3", "prof": "SHS50x50x3.0", "a": [xs[0] + 25, y, z0 + 550],
             "b": [xs[-1] - 25, y, z0 + 550], "ends": [None, None]},
            {"id": "toe", "t": "HR4", "prof": "FL100x6", "a": [xs[0] + 25, y - 22, z0 + 50],
             "b": [xs[-1] - 25, y - 22, z0 + 50], "up": [0, 1, 0], "ends": [None, None]}]
    parts = geometry.build({"profiles": prof, "members": mem})
    for q in parts:
        q["prof"] = next(m["prof"] for m in mem if m["t"] == q["t"])
    d["layers"].append({"k": "hr", "n": "Handrail (test)", "c": "#d4a017"})
    li = len(d["layers"]) - 1
    d["cats"].append({"code": "Z", "title": "HANDRAIL (TEST FIXTURE)", "layers": [li], "dwg": "test"})
    d["groups"].append({"level": "asm", "name": "HR test handrail on UB42 north TC"})
    g = len(d["groups"]) - 1
    d["profs"]["SHS50x50x3.0"] = {"d": "50", "w": "50", "t": "3", "cat": "SHS", "kgm": 4.25, "src": "test fixture"}
    d["profs"]["FL100x6"] = {"d": "100", "w": "6", "t": "", "cat": "FL", "kgm": 4.71, "src": "test fixture"}
    for q in parts:
        q["ref"] = {"HR1": "X-UB42-HRP01", "HR2": "X-UB42-HRT01", "HR3": "X-UB42-HRM01", "HR4": "X-UB42-TB01"}[q["t"]]
        q.update({"layer": li, "unit": tc["unit"], "lu": lu, "tw": tw, "asm": g, "sub": -1, "src": "test fixture", "grid": "-"})
        d["parts"].append(q)
    kg = sum(q["kg"] for q in parts)
    run = sum(q["L"] for q in parts if q.get("rail") == "top")
    # grating + bondek package next to the handrail, each in its own category (MTO overrides via "mto")
    x0, x1 = -15000.0, -10500.0
    prof2 = {"GRT32": {"type": "PL", "b": 1000, "t": 32, "kgm": 39.5}, "DECK": {"type": "PL", "b": 1600, "t": 55, "kgm": 13.3},
             "EDGE": {"type": "PL", "b": 150, "t": 1.2, "kgm": 1.5}, "STUD": {"type": "PL", "b": 19, "t": 19, "kgm": 2.2}}
    zt = z0 + 200
    mem2 = [{"id": "grt", "t": "GRT1", "prof": "GRT32", "a": [x0, y - 1200, zt], "b": [x1, y - 1200, zt], "ends": [None, None],
             "mto": {"kind": "area", "kgm": 39.5, "cat": "GRT", "wid": 1000, "desc": "Grating 32x5 @ 30 (kg/m2)"}},
            {"id": "deck", "t": "BDK1", "prof": "DECK", "a": [x0, y - 3000, zt], "b": [x1, y - 3000, zt], "ends": [None, None],
             "mto": {"kind": "measure", "uom": "m2", "cat": "Deck", "wid": 1600, "desc": "Bondek II 1.0 BMT (m2)", "assumed": ["desc"]}},
            {"id": "edge", "t": "EF1", "prof": "EDGE", "a": [x0, y - 3800, zt + 75], "b": [x1, y - 3800, zt + 75], "up": [0, 1, 0], "ends": [None, None],
             "mto": {"kind": "measure", "uom": "m", "cat": "Edge", "desc": "Edgeform 1.2 BMT (m)"}}]
    mem2 += [{"id": f"stud{k}", "t": "SS1", "prof": "STUD", "a": [x0 + 300 * k, y - 3000, zt - 100], "b": [x0 + 300 * k, y - 3000, zt],
              "up": [1, 0, 0], "ends": [None, None], "mto": {"kind": "measure", "uom": "pcs", "cat": "Stud", "desc": "Shear stud 19x100 (pcs)"}}
             for k in range(3)]
    p2 = geometry.build({"profiles": prof2, "members": mem2})
    for code, title, lname, marks in (("Y", "GRATING (TEST)", "Grating (test)", ("GRT1",)), ("X", "BONDEK PACKAGE (TEST)", "Bondek (test)", ("BDK1", "EF1", "SS1"))):
        d["layers"].append({"k": code.lower(), "n": lname, "c": "#888888"})
        d["cats"].append({"code": code, "title": title, "layers": [len(d["layers"]) - 1], "dwg": "test"})
        d["groups"].append({"level": "asm", "name": f"{title.title()} assembly"})
        for q in p2:
            if q["t"] in marks:
                q.update({"layer": len(d["layers"]) - 1, "unit": tc["unit"], "lu": lu, "tw": tw, "asm": len(d["groups"]) - 1, "sub": -1, "src": "test fixture", "grid": "-"})
    for k_, v_ in (("GRT32", "Grating"), ("DECK", "Bondek"), ("EDGE", "Edgeform"), ("STUD", "Stud")):
        d["profs"][k_] = {"d": "", "w": "", "t": "", "cat": v_, "kgm": prof2[k_]["kgm"], "src": "test fixture"}
    for q in p2:
        q["prof"] = next(m["prof"] for m in mem2 if m["t"] == q["t"])
        d["parts"].append(q)
    (OUT / "rules.data.json").write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
    return kg, run


async def main():
    OUT.mkdir(exist_ok=True)
    kg, run = fixture()
    subprocess.run([sys.executable, "-I", str(ROOT / "build_model.py"), str(OUT / "rules.data.json"), str(OUT / "rules.html")], check=True)
    async with async_playwright() as pw:
        br = await pw.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = await br.new_page(viewport={"width": 1500, "height": 900})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        await page.route("**/*", handler)
        await page.goto("file://" + str(OUT / "rules.html"))
        await page.wait_for_function("window.__model", timeout=240000)
        # 1. tap a handrail post, then step up to "Assembly" (same calls as the tap handler)
        asm_txt = await page.evaluate("""() => { const M = window.__model;
            const i = M.parts.find(p => p.t === 'HR1').i; const ch = chainFor(i);
            const k = ch.findIndex(c => c.name.startsWith('Assembly'));
            select(ch[k].ids, ch, k); return document.querySelector('#info').innerText; }""")
        part_txt = await page.evaluate("""() => { const M = window.__model;
            const i = M.parts.find(p => p.t === 'X-UB42-2DG02').i; const ch = chainFor(i);
            select(ch[0].ids, ch, 0); return document.querySelector('#info').innerText; }""")
        # 3. search by Yang tag and by original tag segment
        res = {}
        for q in ("TC", "2DG02", "HR2", "HRT01", "X-UB42-HR"):
            await page.fill("#q", q)
            await page.dispatch_event("#q", "input")
            res[q] = await page.eval_on_selector_all("#res button", "bs => bs.slice(0, 3).map(b => b.innerText.replace(/\\n/g, ' '))")
        await page.screenshot(path=str(OUT / "rules.png"))
        b64 = await page.evaluate("""async () => { const wb = buildWorkbook(window.__model.mtoSpec(null)); const buf = await wb.xlsx.writeBuffer();
            let s = ''; const u = new Uint8Array(buf); for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); }""")
        card = await page.inner_text("#cCount")
        (OUT / "rules_mto.xlsx").write_bytes(__import__("base64").b64decode(b64))
        await br.close()
    print("expected kg/m", round(kg / (run / 1000), 1), "kg", round(kg, 2), "run", run)
    print("errors:", errs)
    print("ASSEMBLY INFO:", asm_txt.replace("\n", " | "))
    print("PART INFO (UB42 diagonal):", part_txt.replace("\n", " | ")[:260])
    for q, r in res.items():
        print(f"search {q!r}: {r}")
    print("header card:", card)
    import openpyxl
    subprocess.run(["soffice", "--headless", "--convert-to", "xlsx", "--outdir", str(OUT / "calc"), str(OUT / "rules_mto.xlsx")], check=True, capture_output=True, timeout=180)
    wb = openpyxl.load_workbook(OUT / "calc" / "rules_mto.xlsx", data_only=True)
    ws = wb["UB42"]
    for r in range(8, ws.max_row + 1):
        lab = str(ws.cell(r, 9).value or "")
        if lab in ("Sub-Total Z", "Sub-Total Y", "Sub-Total X"):
            print(f"MTO {lab}: kg {ws.cell(r, 18).value} | painted {ws.cell(r, 19).value} | run m {ws.cell(r, 20).value} | area m2 {ws.cell(r, 21).value} | kg/m run {ws.cell(r, 22).value!r}")
        if ws.cell(r, 10).value in ("SS1", "BDK1", "EF1", "GRT1", "HR2"):
            print(f"   row {ws.cell(r, 10).value}: K {ws.cell(r, 11).value} L {ws.cell(r, 13).value} W {ws.cell(r, 14).value} qty {ws.cell(r, 16).value} kg {ws.cell(r, 18).value} run {ws.cell(r, 20).value} area {ws.cell(r, 21).value}")


if __name__ == "__main__":
    asyncio.run(main())
