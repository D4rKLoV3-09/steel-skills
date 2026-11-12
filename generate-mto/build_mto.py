#!/usr/bin/env python3
"""Build a steel MTO workbook: Summary matrix (categories x units) + one Qty-Breakdown sheet per unit.
Usage:  python3 build_mto.py spec.json out.xlsx      (spec format: see SKILL.md)
Summary notes: "decisions" (shown first, only when present), "assumptions", "left_out" ("Nothing left out." when empty).
Unit-sheet columns A..W: Item | Material Section (B:F) | Category | Grade | Description | Mark |
Unit wt | Surface area m2/m | Length | Width | Thk | Qty | Set | Weight | Painted area m2 |
Run (m) | Area (m2) | kg/m run | Dim source (last).  Every category appears on every
unit sheet (empty ones show Sub-Total 0) so the Summary rows stay aligned A..K across all units.
Row kinds: length | plate | piece | area (grating: kg/m2 x L x W) | measure (no weight: uom m2 / m / pcs,
e.g. the Bondek package). Run (m) = len x qty x set on rows with "run": true (handrail top rail) and on
measure rows in m (edgeform); Area (m2) = L x W x qty x set on area rows and measure rows in m2 (bondek);
kg/m run on Sub-Totals and on the Summary = weight / run (handrail in its own category).
"""
import json, sys
from openpyxl import Workbook
from openpyxl.styles import Font, Border, Side, Alignment, PatternFill
from openpyxl.utils import get_column_letter as CL

FONT = "Times New Roman"
BLUE, GREEN = "000000FF", "00008000"
thin, dbl = Side(style="thin"), Side(style="double")
HDR_B = Border(left=thin, right=thin, top=thin, bottom=dbl)
SUB_B = Border(top=thin, bottom=thin)
TOT_B = Border(top=thin, bottom=dbl)
RED_FILL = PatternFill("solid", fgColor="FFC7CE")     # ASSUMED value
PURPLE_FILL = PatternFill("solid", fgColor="E4D7F5")  # SCALED value
HDR_FILL = PatternFill("solid", fgColor="EDEDED")


def f(sz=11, b=False, color=None, u=None):
    return Font(name=FONT, size=sz, bold=b, color=color, underline=u)


def title_block(ws, h, vcol=3):
    for i, (lab, key) in enumerate([("CLIENT'S : ", "client"), ("PROJECT : ", "project"),
                                    ("DESCRIPTION : ", "description"),
                                    ("CONTRACTOR : ", "contractor"), ("DATE : ", "date")], 1):
        ws.cell(i, 1, lab).font = f(b=True)
        ws.cell(i, vcol, h.get(key, "")).font = f()


UOMS = ("m2", "m", "pcs")


def kind(r):
    if r.get("kind"):
        return r["kind"]
    if r.get("wid") and r.get("thk") and not r.get("kgm"):
        return "plate"
    return "length" if r.get("len") else "piece"


UNIT_COLS = ["Item", "Material Section", None, None, None, None, "Category", "Grade", "Description",
             "Mark", "Unit wt. (kg/m, kg/m2) / kg/no", "Surface area (m2/m)", "Length (mm)", "Width (mm)",
             "Thk (mm)", "Qty (no)", "Set (no)", "Weight (kg)", "Painted area (m2)", "Run (m)", "Area (m2)",
             "kg/m run", "Dim source / basis"]
UNIT_W = [6, 7, 3, 7, 3, 7, 9, 9, 58, 8, 13, 12, 11, 10, 8, 8, 7, 13, 13, 11, 11, 10, 70]
NC = len(UNIT_COLS)  # 23 columns A..W: K unit wt | L m2/m | M-O dims | P qty | Q set | R weight | S painted | T run | U area | V kg/m run | W source
SRC = NC
FIELD_COL = {"cat": 7, "grade": 8, "desc": 9, "mark": 10, "kgm": 11, "m2m": 12, "len": 13, "wid": 14,
             "thk": 15, "qty": 16, "set": 17}
INPUT_COLS = (11, 12, 13, 14, 15, 16, 17)
NUMFMT = {11: "0.0##", 12: "0.00#", 13: "#,##0", 14: "#,##0", 15: "0.#", 16: "#,##0", 17: "#,##0", 18: "#,##0.0", 19: "#,##0.0",
          20: "#,##0.00", 21: "#,##0.00", 22: "0.0"}
CENTER = (1, 7, 8, 10, 16, 17, 19, 20, 21, 22)


def unit_sheet(wb, spec, unit):
    ws = wb.create_sheet(unit["name"])
    title_block(ws, spec["header"], 5)
    note = f"   ({unit['note']})" if unit.get("note") else ""
    ws.cell(6, 1, f"QTY-BREAKDOWN : {unit['name']}{note}").font = f(12, True)
    ws.cell(6, SRC, "Red fill = ASSUMED   Purple fill = SCALED   Blue font = input").font = f(9, True)
    ws.cell(6, SRC).alignment = Alignment(horizontal="right")
    for c, t in enumerate(UNIT_COLS, 1):
        cell = ws.cell(7, c, t)
        cell.font, cell.border, cell.fill = f(b=True), HDR_B, HDR_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.merge_cells("B7:F7")
    ws.row_dimensions[7].height = 32
    ws.page_setup.orientation, ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = "landscape", 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "7:7"
    for i, w in enumerate(UNIT_W, 1):
        ws.column_dimensions[CL(i)].width = w
    ws.freeze_panes = "A8"

    r, subs = 8, {}
    for cat in spec["categories"]:
        code = cat["code"]
        ws.cell(r, 1, code).font = f(13, True)
        ws.cell(r, 1).alignment = Alignment(horizontal="center")
        ws.cell(r, 9, cat["title"]).font = f(13, True, u="single")
        dwg = unit.get("dwg", {}).get(code, cat.get("dwg", ""))
        ws.cell(r + 1, 9, f"Dwg No: {dwg}" if dwg else "Dwg No: -").font = f(b=True)
        r += 2
        first = r
        for n, row in enumerate(unit.get("rows", {}).get(code, []), 1):
            k = kind(row)
            if k == "measure":
                assert row.get("uom") in UOMS, f"{unit['name']} {code}: measure row needs uom in {UOMS}"
            vals = {1: n, 7: row.get("cat"), 8: row.get("grade"), 9: row.get("desc"),
                    10: row.get("mark"), 11: row.get("kgm"), 12: row.get("m2m"), 13: row.get("len"),
                    14: row.get("wid"), 15: row.get("thk"), 16: row.get("qty", 1),
                    17: row.get("set", 1), SRC: row.get("src")}
            if k == "length" and row.get("d") is not None:
                vals.update({2: str(row["d"]), 3: "x", 4: str(row.get("w", ""))})
                if row.get("t") not in (None, ""):
                    vals.update({5: "x", 6: str(row["t"])})
            for c, v in vals.items():
                if v is not None:
                    cell = ws.cell(r, c, v)
                    cell.font = f(9 if c == SRC else 11, color=BLUE if c in INPUT_COLS else None)
                    if c in NUMFMT:
                        cell.number_format = NUMFMT[c]
                    if c in CENTER:
                        cell.alignment = Alignment(horizontal="center", vertical="top")
                    elif c == SRC:
                        cell.alignment = Alignment(wrap_text=False, vertical="top")   # Dim source / basis: never wrap
            for key, fill in (("scaled", PURPLE_FILL), ("assumed", RED_FILL)):   # red wins over purple
                for fld in row.get(key, []):
                    ws.cell(r, FIELD_COL[fld]).fill = fill
            if k == "length":
                fm = f"=K{r}*M{r}/1000*P{r}*Q{r}"
            elif k == "plate":
                dens = row.get("dens", 7.85)   # 8.08 for chequered plate (Consteel)
                fm = f"=M{r}/1000*N{r}/1000*O{r}*{dens}*P{r}*Q{r}"
            elif k == "area":                                     # grating: kg/m2 x area
                fm = f"=K{r}*M{r}/1000*N{r}/1000*P{r}*Q{r}"
            elif k == "measure":                                  # bondek package: counted, not weighed
                fm = None
            else:
                fm = f"=K{r}*P{r}*Q{r}"
            if fm:
                p = ws.cell(r, 18, fm)
                p.font, p.number_format, p.alignment = f(), NUMFMT[18], Alignment(vertical="top")
            run = f"=M{r}/1000*P{r}*Q{r}" if row.get("run") or (k == "measure" and row["uom"] == "m") else None
            area = f"=M{r}/1000*N{r}/1000*P{r}*Q{r}" if k == "area" or (k == "measure" and row["uom"] == "m2") else None
            for c, v in ((20, run), (21, area)):
                if v:
                    ws.cell(r, c, v).font = f()
                    ws.cell(r, c).number_format, ws.cell(r, c).alignment = NUMFMT[c], Alignment(horizontal="center", vertical="top")
            if k == "length" and row.get("m2m") is not None:      # painted area = m2/m x length
                pa = f"=L{r}*M{r}/1000*P{r}*Q{r}"
            elif k == "plate":                                    # both faces, edges ignored
                pa = f"=2*M{r}/1000*N{r}/1000*P{r}*Q{r}"
            else:
                pa = None
            if pa:
                ws.cell(r, 19, pa).font = f()
                ws.cell(r, 19).number_format, ws.cell(r, 19).alignment = NUMFMT[19], Alignment(horizontal="center", vertical="top")
            for c in range(1, NC + 1):                       # one consistent vertical alignment per row
                a = ws.cell(r, c).alignment
                ws.cell(r, c).alignment = Alignment(horizontal=a.horizontal, vertical="top", wrap_text=a.wrap_text)
            r += 1
        last = r - 1
        ws.cell(r, 9, f"Sub-Total {code}")
        ws.cell(r, 18, f"=SUM(R{first}:R{last})" if last >= first else 0)
        ws.cell(r, 19, f"=SUM(S{first}:S{last})" if last >= first else 0)
        ws.cell(r, 20, f"=SUM(T{first}:T{last})" if last >= first else 0)
        ws.cell(r, 21, f"=SUM(U{first}:U{last})" if last >= first else 0)
        ws.cell(r, 22, f'=IF(AND(T{r}>0,R{r}>0),R{r}/T{r},"")')
        for c in range(1, NC + 1):
            ws.cell(r, c).border = SUB_B
            ws.cell(r, c).font = f(b=True)
        ws.cell(r, 18).number_format = ws.cell(r, 19).number_format = "#,##0"
        ws.cell(r, 20).number_format = ws.cell(r, 21).number_format = "#,##0.0"
        ws.cell(r, 22).number_format = NUMFMT[22]
        subs[code] = r
        r += 2
    total_row = r
    ws.cell(r, 9, f"TOTAL {unit['name']} (kg)")
    ws.cell(r, 18, "=" + "+".join(f"R{x}" for x in subs.values()))
    ws.cell(r, 19, "=" + "+".join(f"S{x}" for x in subs.values()))
    ws.cell(r, 20, "=" + "+".join(f"T{x}" for x in subs.values()))
    ws.cell(r, 21, "=" + "+".join(f"U{x}" for x in subs.values()))
    for c in range(1, NC + 1):
        ws.cell(r, c).border = TOT_B
        ws.cell(r, c).font = f(12, True)
    ws.cell(r, 18).number_format = ws.cell(r, 19).number_format = "#,##0"
    ws.cell(r, 20).number_format = ws.cell(r, 21).number_format = "#,##0.0"
    return subs, total_row


def summary_sheet(ws, spec, links):
    cur = spec.get("currency", "RM")
    units = [u["name"] for u in spec["units"]]
    n = len(units)
    tcol, ucol, rcol, acol = 3 + n, 4 + n, 5 + n, 6 + n
    T, R, A, last = CL(tcol), CL(rcol), CL(acol), CL(acol)
    title_block(ws, spec["header"])
    heads = ["Sl. No.", "Description"] + units + ["Total (kg)", "Unit", f"Rate ({cur})", f"Amount ({cur})", "Painted area (m2)",
                                              "Run (m)", "Area (m2)", "kg/m run"]
    for c, t in enumerate(heads, 1):
        cell = ws.cell(7, c, t)
        cell.font, cell.border, cell.fill = f(b=True), HDR_B, HDR_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[7].height = 32
    ws.page_setup.orientation, ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = "landscape", 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    widths = [7, 80] + [13] * n + [14, 7, 11, 13, 16, 11, 11, 10]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[CL(i)].width = w

    rates = spec.get("rates", {})
    r = 8
    for cat in spec["categories"]:
        code = cat["code"]
        ws.cell(r, 1, code).font = f(13, True)
        ws.cell(r, 1).alignment = Alignment(horizontal="center")
        ws.cell(r, 2, cat["title"]).font = f(b=True)
        ws.cell(r, 2).alignment = Alignment(wrap_text=True, vertical="center")
        for j, u in enumerate(units):
            c = ws.cell(r, 3 + j, f"='{u}'!R{links[u][0][code]}")
            c.font, c.number_format = f(color=GREEN), "#,##0"
        c = ws.cell(r, tcol, f"=SUM(C{r}:{CL(2 + n)}{r})")
        c.font, c.number_format = f(b=True), "#,##0"
        ws.cell(r, ucol, "kg").font = f()
        pc = ws.cell(r, acol + 1, "=" + "+".join(f"'{u}'!S{links[u][0][code]}" for u in units))
        pc.font, pc.number_format = f(color=GREEN), "#,##0.0"
        for k, col in ((2, "T"), (3, "U")):
            c = ws.cell(r, acol + k, "=" + "+".join(f"'{u}'!{col}{links[u][0][code]}" for u in units))
            c.font, c.number_format = f(color=GREEN), "#,##0.0"
        rn = CL(acol + 2)
        c = ws.cell(r, acol + 4, f'=IF(AND({rn}{r}>0,{T}{r}>0),{T}{r}/{rn}{r},"")')
        c.font, c.number_format = f(b=True), "0.0"
        if code in rates:
            ws.cell(r, rcol, rates[code]).font = f(color=BLUE)
            c = ws.cell(r, acol, f"={T}{r}*{R}{r}")
            c.font, c.number_format = f(), "#,##0.00"
        r += 1
    first, lastcat = 8, r - 1
    ws.cell(r, 2, "Sub-Total per unit (kg)" if "unit_label" not in spec else f"Sub-Total per {spec['unit_label']} (kg)")
    for c in range(3, tcol + 1):
        col = CL(c)
        ws.cell(r, c, f"=SUM({col}{first}:{col}{lastcat})").number_format = "#,##0"
    if rates:
        ws.cell(r, acol, f"=SUM({A}{first}:{A}{lastcat})").number_format = "#,##0.00"
    for c in range(1, acol + 5):
        ws.cell(r, c).border, ws.cell(r, c).font = SUB_B, f(b=True)
    sub = r
    for k in (1, 2, 3):
        ps = ws.cell(r, acol + k, f"=SUM({CL(acol + k)}{first}:{CL(acol + k)}{lastcat})")
        ps.font, ps.number_format = f(b=True), "#,##0.0"
    r += 1
    sheet_word = spec.get("unit_label", "unit")
    ws.cell(r, 2, f"Check: {sheet_word} sheet total (kg)").font = f(10)
    for j, u in enumerate(units):
        c = ws.cell(r, 3 + j, f"='{u}'!R{links[u][1]}")
        c.font, c.number_format = f(10, color=GREEN), "#,##0"
    # optional connection / misc allowance: % input (blue, default 0) -> kg per unit
    r += 1
    pct = r
    ws.cell(r, 2, "Connection / misc. allowance (%) - 0 when plates and bolts are itemised").font = f()
    c = ws.cell(r, tcol, spec.get("allowance", 0))
    c.font, c.number_format = f(color=BLUE), "0.0%"
    r += 1
    ws.cell(r, 2, "Allowance (kg)").font = f()
    for c in range(3, tcol + 1):
        col = CL(c)
        cell = ws.cell(r, c, f"={col}{sub}*${T}${pct}")
        cell.font, cell.number_format = f(), "#,##0"
    allow = r
    r += 2
    label = spec.get("grand_total_label", f"{n} UNITS")
    ws.cell(r, 2, f"GRAND TOTAL - {label} (kg)")
    ws.cell(r, tcol, f"={T}{sub}+{T}{allow}").number_format = "#,##0"
    ws.cell(r + 1, 2, f"GRAND TOTAL - {label} (tonnes)")
    ws.cell(r + 1, tcol, f"={T}{r}/1000").number_format = "#,##0.00"
    for rr in (r, r + 1):
        for c in range(1, acol + 5):
            ws.cell(rr, c).border, ws.cell(rr, c).font = TOT_B, f(12, True)
    r += 2
    # notes for Yang, most urgent first: decisions (only when there are any), assumptions, left out
    sections = [("DECISIONS FOR YOU", spec.get("decisions", []))] if spec.get("decisions") else []
    sections += [("ASSUMPTIONS / ITEMS TO VERIFY", spec.get("assumptions", [])),
                 ("LEFT OUT OF THIS TAKE-OFF", spec.get("left_out") or ["Nothing left out."])]
    for title, items in sections:
        r += 2
        ws.cell(r, 1, title).font = f(12, True)
        for a in items:
            r += 1
            ws.cell(r, 1, "-").font = f(10)
            ws.cell(r, 1).alignment = Alignment(horizontal="right", vertical="top")
            c = ws.cell(r, 2, a)
            c.font, c.alignment = f(10), Alignment(wrap_text=True, vertical="top")
            ws.merge_cells(f"B{r}:{last}{r}")
            ws.row_dimensions[r].height = 15 * max(2, -(-len(a) // 170))


def build(spec, out):
    codes = [c["code"] for c in spec["categories"]]
    assert len(codes) == len(set(codes)), "duplicate category codes"
    for u in spec["units"]:
        bad = set(u.get("rows", {})) - set(codes)
        assert not bad, f"{u['name']}: rows under unknown categories {bad}"
    wb = Workbook()
    summ = wb.active
    summ.title = "Summary "
    links = {u["name"]: unit_sheet(wb, spec, u) for u in spec["units"]}
    summary_sheet(summ, spec, links)
    for u in spec["units"]:                      # print A:V; the long unwrapped source column W stays on screen
        wb[u["name"]].print_area = f"A1:V{wb[u['name']].max_row}"
    wb.save(out)
    return links


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    links = build(spec, sys.argv[2])
    for u, (subs, tot) in links.items():
        print(u, "subtotal rows", subs, "total row", tot)
    print("saved", sys.argv[2])
