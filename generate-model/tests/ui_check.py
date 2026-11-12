#!/usr/bin/env python3
"""Toolbar / panel behaviour in a real browser.

    python tests/ui_check.py PAGE.html

- tower chip: flies to the unit and selects it (breadcrumb at the tower level)
- Labels button beside Grid: toggles labels, kept in step with the Layers checkbox
- panel stays on the right at desktop, tablet and phone widths
- selection chain names from the data (group label, e.g. "Columns")
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.async_api import async_playwright  # noqa: E402
from regress import handler  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "out"


async def main(html):
    ok = True
    async with async_playwright() as pw:
        br = await pw.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = await br.new_page(viewport={"width": 1400, "height": 850})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        await page.route("**/*", handler)
        await page.goto("file://" + str(pathlib.Path(html).resolve()))
        await page.wait_for_function("window.__model", timeout=240000)
        await page.wait_for_timeout(3000)
        # tower chip
        await page.click("#chips button:text-is('Truss UB42')")
        await page.wait_for_timeout(1500)
        r = await page.evaluate("""() => ({crumbs: [...document.querySelectorAll('#crumbs button')].map(b => b.innerText + (b.classList.contains('on') ? '*' : '')),
            n: window.__model.S.sel.length, unit: [...new Set(window.__model.S.sel.map(i => window.__model.parts[i].unit))].map(u => D.units[u]),
            name: document.querySelector('#info').innerText.split('\\n')[0]})""")
        good = r["n"] == 204 and r["unit"] == ["Truss UB42"]
        ok &= good
        chips = await page.eval_on_selector_all("#chips button", "bs => bs.map(b => b.innerText)")
        good &= all(c.startswith("Truss ") or c == "Columns + frames" for c in chips)
        print("chips:", chips)
        print("chip Truss UB42 ->", r, "OK" if good else "FAIL")
        await page.screenshot(path=str(OUT / "ui_chip.png"))
        # Labels button
        before = await page.evaluate("() => [window.__model.S.labels, document.querySelector('#cLabels').checked]")
        await page.click("#bLab")
        after = await page.evaluate("() => [window.__model.S.labels, document.querySelector('#cLabels').checked, document.querySelector('#bLab').classList.contains('on'), [...document.querySelectorAll('#tb button')].map(b => b.innerText).slice(-3)]")
        good = before == [True, True] and after[:3] == [False, False, False] and after[3][-2:] == ["Labels", "Measure"]
        ok &= good
        print("Labels button:", before, "->", after, "OK" if good else "FAIL")
        await page.click("#bLab")
        # chain names: a column, three taps up to its top level; and UB41 lift unit contents
        r = await page.evaluate("""() => { const M = window.__model;
            const col = M.parts.find(p => p.t === 'UC1').i; const ch = chainFor(col);
            const lu41 = M.parts.filter(p => D.groups[p.lu].name === 'Truss UB41');
            const box = M.parts.filter(p => D.groups[p.lu].name === 'Box tower FB-BS2');
            return {column_chain: ch.map(c => c.name), ub41: [lu41.length, Math.round(lu41.reduce((a, p) => a + p.kg, 0))],
                    box_has: ['UB38', 'UB42', 'UB45'].map(t => box.some(p => p.t === t))}; }""")
        good = r["column_chain"][-1].endswith("Columns") and all(r["box_has"])
        ok &= good
        print("column chain", r["column_chain"], "| UB41 lift unit parts/kg", r["ub41"], "| UB38/UB42/UB45 in box tower", r["box_has"], "OK" if good else "FAIL")
        # panel on the right at three widths
        for w, h in ((1400, 850), (900, 700), (700, 800), (420, 860)):
            await page.set_viewport_size({"width": w, "height": h})
            await page.wait_for_timeout(400)
            g = await page.evaluate("""() => { const v = document.querySelector('#view').getBoundingClientRect(), p = document.querySelector('#panel').getBoundingClientRect();
                return {view: [Math.round(v.left), Math.round(v.width)], panel: [Math.round(p.left), Math.round(p.width), Math.round(p.top)], scrollX: document.documentElement.scrollWidth > innerWidth}; }""")
            good = g["panel"][0] >= g["view"][0] + g["view"][1] - 1 and not g["scrollX"]
            ok &= good
            print(f"  {w}px: view x/w {g['view']}  panel x/w/top {g['panel']}  side scroll {g['scrollX']}  {'right OK' if good else 'FAIL'}")
            if w == 700:
                await page.screenshot(path=str(OUT / "ui_700.png"))
        await br.close()
    print("page errors:", errs or "none")
    print("ALL OK" if ok and not errs else "FAILED")
    return 0 if ok and not errs else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1])))
