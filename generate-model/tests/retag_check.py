#!/usr/bin/env python3
"""After a retag: weights per MTO category must not change; both tags must be searchable.

    python tests/retag_check.py BASE.html RETAGGED.html
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.async_api import async_playwright  # noqa: E402
from regress import handler  # noqa: E402

TOTALS = """() => { const sp = window.__model.mtoSpec(null); const out = {};
  for (const u of sp.units) for (const [c, rows] of Object.entries(u.rows)) for (const r of rows){
    const kg = r.kind === 'plate' ? r.len / 1000 * r.wid / 1000 * r.thk * 7.85 * r.qty : (r.kgm || 0) * (r.len || 0) / 1000 * r.qty;
    out[u.name + ' ' + c] = (out[u.name + ' ' + c] || 0) + kg; }
  return out; }"""


async def load(br, html):
    page = await br.new_page(viewport={"width": 1400, "height": 850})
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    await page.route("**/*", handler)
    await page.goto("file://" + str(pathlib.Path(html).resolve()))
    await page.wait_for_function("window.__model", timeout=240000)
    return page, errs


async def main(base, new):
    async with async_playwright() as pw:
        br = await pw.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pa, ea = await load(br, base)
        pb, eb = await load(br, new)
        ta, tb = await pa.evaluate(TOTALS), await pb.evaluate(TOTALS)
        res = {}
        for q in ("TC2", "W18", "2DG02", "X-UB42-TC", "SC01", "UB1"):
            await pb.fill("#q", q)
            await pb.dispatch_event("#q", "input")
            res[q] = await pb.eval_on_selector_all("#res button", "bs => bs.slice(0, 3).map(b => b.innerText.replace(/\\n/g, ' '))")
        info = await pb.evaluate("""() => { const i = window.__model.parts.find(p => p.ref === 'X-UB42-2DG02').i;
            const ch = chainFor(i); select(ch[0].ids, ch, 0); return document.querySelector('#info').innerText.replace(/\\n/g, ' | '); }""")
        card = await pb.inner_text("#cCount")
        await br.close()
    bad = [k for k in set(ta) | set(tb) if abs(ta.get(k, 0) - tb.get(k, 0)) > 1e-6]
    print(f"category weights: {len(ta)} unit x category cells, differences: {len(bad)} {bad[:5]}")
    print("page errors:", ea + eb or "none")
    print("header card:", card)
    print("info:", info[:230])
    for q, r in res.items():
        print(f"search {q!r}: {r}")
    return 0 if not bad and not (ea + eb) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2])))
