---
name: "generate-mto"
description: "Steel material take-off (MTO/weight/tonnage/BOQ) for any steel structure, as Yang's MTO Excel (one sheet per unit, categories A-K, Grade column) with Consteel unit weights. Use for /generate-MTO, take-off, how heavy, tonnage."
---

# Generate MTO

**Deliver** one .xlsx in Yang's MTO format: a `Summary ` sheet (categories x units, grand total kg and tonnes, allowance, assumptions) + one Qty-Breakdown sheet per unit. Every weight is a live formula, every unit weight comes from the **Consteel catalogue**, every row says where its dimensions came from. A single structure = one unit sheet. This skill replaces `steel-material-takeoff`.

Why: one sheet per unit (a unit that differs is visible and editable alone); the same lettered categories on every sheet (the Summary reads as a matrix); traceability (every row leads to a drawing dimension, a catalogue kg/m and a counted quantity).

## Setup (once per session)
In Claude Code you are already in the repo; in a claude.ai cloud session attach Yang's private repo (`add_repo` owner `D4rKLoV3-09`, repo `steel-skills`) and clone it. Drawings come from `jobs/<job>/`, the workbook goes to `jobs/<job>/out/`. Use `generate-mto/build_mto.py` (spec.json -> workbook) and `generate-mto/references/consteel_catalogue.md` (Consteel 2025 kg/m and m2/m: **grep it for the sections you need, never read it whole**). Read the builder's docstring, not the code, unless changing it. **This agent owns the MTO format:** `build_mto.py` and its ExcelJS port `port/mto_workbook.js` (generate-model injects the port into every model page at build time). Change both together, run `tests/mto_parity.py <a built model page>` and `tests/test_columns.py`, commit. The agent definition is `.claude/agents/generate-mto.md`.

## Workflow
1. **Read the inputs** (drawings, Tekla/IFC reports, model part lists, previous MTOs, revisions Yang describes). Title block and revision status first (Rule A). PDF drawings: if `jobs/<job>/out/read/reading.json` exists (the model agent already read them) start from it; otherwise run `drawings/read_drawings.py` and read `index.md`, then look only at crops from `drawings/crop.py` (generate-model skill section 1), and write `reading.json`.
2. **Units:** one sheet per physical unit, named with its own mark, in site/drawing order. Identical units still get their own sheet unless Yang asks for "one sheet x Set".
3. **Categories A, B, C ...** by sub-assembly / erection package, not section type; same list, order and titles on every sheet. **Only what the drawings show:** no category, row or column for something that is not there (no handrail or grating on the drawings = no handrail or grating category); letter the categories that exist consecutively. `build_mto.py` drops a category with no row in any unit and hides the Run / kg/m run and Area columns when no row uses them; a category used by some units keeps Sub-Total 0 on the others. Towers: KSSA A-K template below. Other structures: fabrication/erection order (base frame -> columns / wall frames -> roof -> doors / louvres -> access -> lifting & misc), typically 6-11; if not obvious, show Yang 2 options first. Each category has a `Dwg No:` line. **Handrail, when there is any, gets its own category** (its Sub-Total shows kg/m run); the **Bondek package** has its own category "BONDEK PACKAGE".
4. **Settle the calls that move tonnage** (Rule C) with options; once Yang delegates, decide, label it, move on.
5. **Take off each unit** into spec rows (Rules B-J).
6. **Write spec.json and run** `python3 build_mto.py spec.json <Project>_MTO.xlsx`. Never hand-place cells. Near-identical units: build the base unit's rows once in Python and copy/modify per unit, stating each change in the unit `note` and the assumptions.
7. **Verify**, then deliver. When iterating, rebuild the SAME file name.

## Take-off rules
**A. Title block first.** Sheets in one PDF can belong to different structures. A lower-status sheet ("60% design review", "for information only") is flagged prominently, not treated like Tender/IFC.

**B. Unit weights only from Consteel.** No generic tables or "designation mass" shortcuts (UC254x254x89 is 88.9, SHS150x150x6.3 hot-finished 28.3, UB457x191x98 98.3).
- UB/UC: match the depth group, kg/m and actual D x B. Hollow sections: hot-finished (EN10210) vs cold-formed (EN10219) as the drawing says; if silent ask once, else hot-finished and list it.
- Plates kg = L x W x t x 7.85; chequered plate 8.08 (`"dens": 8.08`). Bolts, studs, proprietary: kg per piece (`piece`), say the source in `src`.
- Size not in the catalogue file: read it from the Consteel PDF if attached; else compute from geometry, write `NOT IN EXTRACTED CONSTEEL TABLE - computed from geometry, verify` in `src` and list it.
- kg/m goes in the blue input cell, catalogue quoted in `src` ("Consteel 2025 UB/UC 88.9").

**C. Flag missing data.** Never silently invent quantities; every assumption stays an editable blue input and goes in ASSUMPTIONS / ITEMS TO VERIFY. A gap that moves the total materially: stop and offer options (number from Yang / ratio estimate / exclude as TBD). Once delegated, make a labelled estimate and don't ask again.

**D. Count carefully.** Scan for sideways labels on vertical members. Undimensioned brace = sqrt(panel w^2 + h^2) node to node, say so in `src`.

**E. Repeats.** Identical units = own sheets. A repeated sub-assembly inside a unit = once, multiplied in `Set`. Near-identical items = separate rows with their own Set.

**F. Marks = Yang's tags (standing rule).** The Mark column always carries Yang's tags: BR bracing, P purlin, UB horizontal beams, UC columns, PLT plates, L angles, BU built-up I, C channels, SH / RH / CH hollow, TC / BC / W truss chord / web, GRT grating, CHQ chequered plate, ST stair, HR handrail, CL cat ladder; BDK / SS / EF for bondek, studs, edgeform. The drawing's or model's own mark goes at the start of `src` as `Ref <original mark>; ...`. Number Yang's marks one-to-one per distinct original mark; one letter reused for genuinely different systems = separate categories or clearly separated rows.

**G. Trace every dimension** to a printed dimension (follow witness lines). Not printed: tag SCALED / ESTIMATED / BACK-CALCULATED with the derivation ("= 12000 bay / 3", "scaled @1:120", "cut length = model weight / kg/m"). Collapse repeats only where the drawing says TYP. A row is done only when `src` names a printed source or carries a tag.

**H. Tapered / built-up without a plate schedule:** ask for the schedule or Yang's assumption; then kg/m = [2 x bf x tf + (d - 2tf) x tw] x 0.00785 at the average depth, flagged ESTIMATED once at the top of the category.

**I. Plates, bolts, grade.** Itemise plates and bolt sets; welded plates go with their member's category. Grade (right of Category): S235/S275/S355/S460 (+ sub-grade if given), bolts G8.8/G10.9, purlins G450, grating/proprietary as specified; none stated = `TBC` and listed. **A grade Claude assumes itself is written `*S275` (with the asterisk).** Connection allowance % on the Summary: 0 when plates and bolts are itemised, 5-8 % only when connections are not detailed (say so).

**J. Painting (every MTO).** Every `length` row has `m2m` (Consteel "Surface Area per metre" from the catalogue file; quote it in `src`). Not in the catalogue: compute (I-sections 2D + 4B - 2tw; hollow perimeter; angles/channels outline perimeter), add `"m2m"` to the row's `assumed` list and the assumptions. Pre-galvanised / galvanised items get no m2m (say so in the assumptions).

**K. Measured quantities (every MTO, standing rule):**
- **Handrail:** `"run": true` on the top-rail rows -> Run (m); the handrail category's Sub-Total and Summary row show **kg/m run**.
- **Grating:** row kind `area`, `kgm` = kg/m2 (from the supplier or assumed and flagged), `len` x `wid` -> Area (m2) and weight.
- **Bondek package (Yang's scope):** bondek always comes with shear studs and edgeform; a slab above Yang's steel means bondek even if not shown. Rows kind `measure` in "BONDEK PACKAGE": deck `uom: "m2"` (len x wid), studs `uom: "pcs"` (qty), edgeform `uom: "m"` (len). No weight, so it stays out of the steel tonnage. Defaults when not stated, ASSUMED: Bondek II 1.0 BMT; studs 19x100 @ 300 single row on every beam under the slab; edgeform 1.2 BMT, height = slab thickness.

## KSSA temporary-tower categories (A-K)
A TOWER BODY - COLUMNS, FRAMES, DIAGONALS · B RAKER FRAME AND SPLICE FRAME BEAMS · C COLUMN SPLICES, PLATES AND BOLTS · D TOP MODULE - HEAD FRAME, DECK FRAME, CHEQUERED PLATE, JOINT CHANNELS · E JACK HEAD - BUILT-UP HEAD BEAMS, STOPPERS, JACK PLATES, PACKS · F TOP-CHORD PROPS, TIES, FIN PLATES AND LIFTING LUGS · G PROPOSED BRACING (STEEL HUB UPGRADE) · H RAKING SUPPORT TRUSSES · I I-BEAM SUPPORTS · J ACCESS - LANDING, LADDERS, DECK RAILS, REST PLATFORM · K STEEL BASE - GRILLAGE AND GRID. Adapt titles; add or drop letters only for a real package; keep letters continuous.

## Workbook layout (made by the builder)
- Summary: title block rows 1-5; row 7 `Sl. No. | Description | <units> | Total (kg) | Unit | Rate | Amount | Painted area (m2) | Run (m) | Area (m2) | kg/m run`; Sub-Total, Check row, allowance %, Allowance, GRAND TOTAL kg and tonnes; then the notes for Yang, always in this order: **CAUTIOUS** (only when there are any: a big member on a small support - deeper than its supporting beam, wider than its column, different sections butting in line; hollow sections and channels too), **LEFT OUT OF THIS TAKE-OFF** (each item with why and sheet; "Nothing left out." when empty), **DECISIONS FOR YOU** (only when there are any), **ASSUMPTIONS / ITEMS TO VERIFY**. These lists live here, not in the reply.
- Unit sheets A-W: `Item | Material Section (B:F) | Category | Grade | Description | Mark | Unit wt (kg/m, kg/m2) / kg/no | Surface area (m2/m) | Length | Width | Thk | Qty | Set | Weight (kg) | Painted area (m2) | Run (m) | Area (m2) | kg/m run | Dim source / basis` (last, 9 pt, never wrapped). Blue = input, green = cross-sheet link, red fill = ASSUMED, purple fill = SCALED (key in the last column of row 6). Prints A:V landscape, one page wide.

## Spec JSON
```json
{"header": {"client": "...", "project": "...", "description": "...", "contractor": "Steel Hub Engineering Sdn. Bhd.", "date": "dd-mm-yyyy"},
 "currency": "RM", "unit_label": "tower", "grand_total_label": "4 TOWERS", "allowance": 0,
 "categories": [{"code": "A", "title": "...", "dwg": "..."}],
 "units": [{"name": "T-NW1", "note": "", "dwg": {"A": "override"}, "rows": {"A": [
   {"kind": "length", "d": "254", "w": "254", "t": "89", "cat": "UC", "grade": "S355", "desc": "UC254x254x89", "mark": "UC1",
    "kgm": 88.9, "m2m": 1.5, "len": 7759, "qty": 20, "set": 1, "src": "Ref TC1; TT-GA-001 printed 7759; Consteel 88.9; m2/m 1.5"},
   {"kind": "plate", "cat": "Plate", "grade": "S275", "desc": "PL30 base 460x460", "mark": "PLT1", "len": 460, "wid": 460, "thk": 30, "qty": 4, "src": "..."},
   {"kind": "piece", "cat": "Bolt", "grade": "G8.8", "desc": "M24 x 90 bolt set", "mark": "BOLT1", "kgm": 0.65, "qty": 16, "src": "..."},
   {"kind": "length", "cat": "CHS", "desc": "CHS48.3x3.2 top rail", "mark": "HR2", "kgm": 3.56, "m2m": 0.152, "len": 6000, "qty": 1, "run": true, "src": "..."},
   {"kind": "area", "cat": "GRT", "grade": "HDG", "desc": "Grating 32x5 @ 30", "mark": "GRT1", "kgm": 39.5, "len": 6000, "wid": 1000, "qty": 2, "assumed": ["kgm"], "src": "..."},
   {"kind": "measure", "uom": "m2", "cat": "Deck", "desc": "Bondek II 1.0 BMT", "mark": "BDK1", "len": 6000, "wid": 3000, "qty": 2, "assumed": ["desc"], "src": "..."}]}}],
 "rates": {"A": 6.5},
 "cautions": ["Tower A: UB10 (Ref B61S, UB610x305x149) butts in line with UB20 (Ref BU09, UC465x421x589) - 6 joints on 4th Storey (S-2224)"],
 "decisions": ["Grating weight: supplier figure, or keep 39.5 kg/m2 (+/- 0.4 t)?"],
 "assumptions": ["..."],
 "left_out": ["Anchor bolts - by others (GA-001 note 4)"]}
```
`assumed` / `scaled` list the fields to fill red / purple (cat, grade, desc, mark, kgm, m2m, len, wid, thk, qty, set). `cat` = the short section label: UC, UB, IPE, HE, H, PFC, TFC, EA, UA, SHS, RHS, CHS, C, Z, FL, Plate, CHQ, Bolt, GRT, Deck, Stud, Edge, Misc.

## Verify before delivering
Recalculate with LibreOffice (`soffice --headless --convert-to xlsx --outdir calc <file>`), then with openpyxl `data_only=True`: zero `#` errors; Sub-Total = Check row per unit; totals plausible against the previous version or the model weight; no row weighs 0 by mistake (bondek `measure` rows excepted); every ASSUMED / SCALED tag in `src` has its cell filled and nothing else is; handrail kg/m run and bondek / grating m2 present where those items exist; every row has a Grade and a `src`; every kg/m is a Consteel value or flagged NOT IN EXTRACTED CONSTEEL TABLE. Fix the spec and rebuild rather than patching cells. Render the Summary and one unit sheet (LibreOffice -> PDF -> PNG) and look: headers readable, nothing clipped, columns in order.

## Delivering
Send the xlsx. Reply in pyramid form: **grand total (t)** -> per-unit totals and the largest categories (%) -> the 3-5 assumptions that move tonnage most. Offer to save it to the project space if it belongs to one.
