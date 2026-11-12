#!/usr/bin/env python3
"""Regression: old page vs page rebuilt from viewer_template.html + same data.

    python tests/regress.py OLD.html NEW.html

Loads both in headless Chromium (CDN scripts routed to local copies, fonts blocked),
then compares: part count, total kg, whole-page text, MTO spec, console errors and
an ISO-view screenshot (pixel diff). Exit code 0 = identical.
Local libs: run npm install in the repo root (package.json pins three 0.128.0 and exceljs 4.4.0) or set VIEWER_LIBS
"""
import asyncio
import hashlib
import json
import os
import pathlib
import sys

from playwright.async_api import async_playwright
import numpy as np
from PIL import Image, ImageChops

LIB = pathlib.Path(os.environ.get(
    "VIEWER_LIBS",
    str(pathlib.Path(__file__).resolve().parents[2] / "node_modules")))
ROUTES = {
    "three.js/r128/three.min.js": LIB / "three/build/three.min.js",
    "three@0.128.0/examples/js/controls/OrbitControls.js": LIB / "three/examples/js/controls/OrbitControls.js",
    "exceljs/4.4.0/exceljs.min.js": LIB / "exceljs/dist/exceljs.min.js",
}
OUT = pathlib.Path(__file__).resolve().parent / "out"


async def handler(route):
    url = route.request.url
    for key, path in ROUTES.items():
        if key in url:
            return await route.fulfill(path=str(path), content_type="application/javascript")
    if url.startswith(("file:", "data:", "blob:")):
        return await route.continue_()
    return await route.abort()


async def snapshot(browser, html, handle, shot_name):
    page = await browser.new_page(viewport={"width": 1500, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    page.on("console", lambda m: errors.append("console: " + m.text) if m.type == "error" and "ERR_FAILED" not in m.text else None)
    await page.route("**/*", handler)
    await page.goto("file://" + str(pathlib.Path(html).resolve()))
    await page.wait_for_function("window.__model || window.__ub4", timeout=240000)
    await page.wait_for_timeout(9000)  # fly animation + slow software rendering must settle
    info = await page.evaluate("""() => { const M = window.__model || window.__ub4;
        return { n: M.parts.length, kg: M.parts.reduce((a, p) => a + (p.kg || 0), 0),
                 body: document.body.innerText, title: document.title,
                 mto: JSON.stringify(M.mtoSpec(null)) } }""")
    OUT.mkdir(exist_ok=True)
    await page.screenshot(path=str(OUT / shot_name))
    await page.close()
    return info, errors


async def main(old, new):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader",
                                                 "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        a, ea = await snapshot(browser, old, "__ub4", "old.png")
        b, eb = await snapshot(browser, new, "__model", "new.png")
        await browser.close()

    ia, ib = Image.open(OUT / "old.png").convert("RGB"), Image.open(OUT / "new.png").convert("RGB")
    diff = ImageChops.difference(ia, ib)
    bbox = diff.getbbox()
    n_diff = int((np.asarray(diff).max(axis=2) > 8).sum()) if bbox else 0
    if bbox:
        diff.point(lambda v: min(255, v * 8)).save(OUT / "diff.png")

    checks = [
        ("part count", a["n"] == b["n"], f"{a['n']} vs {b['n']}"),
        ("total kg", abs(a["kg"] - b["kg"]) < 1e-6, f"{a['kg']:.3f} vs {b['kg']:.3f}"),
        ("page title", a["title"] == b["title"], f"{a['title']!r} vs {b['title']!r}"),
        ("page text (panel, notes, header card)", a["body"] == b["body"], f"{len(a['body'])} vs {len(b['body'])} chars"),
        ("MTO spec", a["mto"] == b["mto"],
         f"sha {hashlib.sha256(a['mto'].encode()).hexdigest()[:10]} vs {hashlib.sha256(b['mto'].encode()).hexdigest()[:10]}, {len(a['mto']):,} chars"),
        ("console errors", sorted(ea) == sorted(eb), f"{len(ea)} vs {len(eb)}"),
        ("ISO screenshot (pixels differing by >8)", n_diff == 0, f"{n_diff} px"),
    ]
    ok = True
    for name, passed, detail in checks:
        ok &= passed
        print(("PASS " if passed else "FAIL ") + name + "  [" + detail + "]")
    if ea or eb:
        print("console errors old:", ea[:5], "| new:", eb[:5])
    if not a["body"] == b["body"]:
        la, lb = a["body"].splitlines(), b["body"].splitlines()
        for i, (x, y) in enumerate(zip(la, lb)):
            if x != y:
                print(f"first text difference at line {i}:\n  old: {x[:200]}\n  new: {y[:200]}")
                break
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2])))
