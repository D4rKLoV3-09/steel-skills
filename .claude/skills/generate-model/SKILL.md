---
name: "generate-model"
description: "Build or revise Yang's interactive 3D steel model artifacts (towers, frames, trusses, enclosures) with concentric zero-gap joints, his member tags, assembly selection and viewer tools."
---

# generate-model

One self-contained three.js page per model, published as an Artifact (same URL for every revision); deliver only the artifact, never a separate HTML file. **The viewer UI and the geometry rules are code in Yang's private repo `D4rKLoV3-09/steel-skills` (folder `generate-model/`). Never re-write the viewer or the clipping by hand: write the job's data and run the scripts.** If anything is ambiguous, offer options before building.

## Setup (once per session)
- In Claude Code you are already in the repo (`CLAUDE.md` says where things are). In a claude.ai cloud session: attach the repo (`add_repo` owner `D4rKLoV3-09`, repo `steel-skills`) and clone it. `npm install` in its root before the browser tests.
- Drawings come from `jobs/<job>/`; results go to `jobs/<job>/out/`; a model's data lives in `models/<name>/`. In Claude Code the page is the HTML file (open it in a browser); in a claude.ai session it is also published as an Artifact.
- Files: `viewer_template.html` (fixed UI), `geometry.py` (spec -> zero-gap prisms; I, SHS, RHS, CHS, LIPC, PL), `build_model.py` (data -> page, validates), `read_drawing.py` (vector PDF -> marks + lines), `ga_plan.py` (GA floor plans -> connected framing: merge / pair / outlines / connect / bondek), `tests/` (regress, rules_check, ui_check, retag_check, ub42_from_old, read_drawing_check, ga_plan_check, clash_check = SAT clash + host-contact gaps on the real prisms, bondek-package parts left out). Read a script's docstring, not the whole file, unless changing it.
- The MTO builder for "the MTO" is `generate-mto/build_mto.py` in the same repo; `node generate-mto/page_mtospec.js PAGE DATA SPEC` gives it the page's own `mtoSpec`.
- **Speed (Yang's rule): a job is one command.** Every model keeps `models/<name>/build.py` (drawings -> spec -> geometry -> data -> clash -> page -> mtoSpec -> MTO -> recalculation checks, a few minutes, prints only what failed). New job = copy the closest model's scripts and change the numbers. While developing: test into the scratch folder, print counts instead of reading spec / data JSON, no agent for what a script does, and put anything reusable into `generate-model/` rather than the job folder.
- Drawing readers for claude.ai cloud sessions (poppler + pdfplumber + opencv; no PyMuPDF there): `drawings/read_drawings.py` (PDF -> text index + thumbnails) and `drawings/crop.py` (one view or one mark as an image); section 1.

## 0. Standing rules and ask-first
- **Member tags:** always Yang's tags (section 4), never the drawing's or a supplied model's own tags. The original tag goes in `ref`; both are searchable.
- **Bondek package (Yang's scope):** bondek always comes with shear studs and edgeform; a slab above Yang's steel means bondek even if not shown. Model deck, studs on every beam under the slab and edgeform at the slab edge, all three on ONE layer "Bondek package" that is hidden when the page opens (`off: true` on the layer), ASSUMED when not on the drawings and listed in Assumptions. Always the standard models built into `geometry.py` (profiles `BONDEK`, `SHEAR STUD`, `EDGEFORM`): one spec line per deck strip (`a`, `b`, `wid`), per stud row (`a`, `b`, `spacing`) and per edge; never draw their geometry and never vary the model with product, thickness or stud length, only `desc` changes (the quantity is what matters). Defaults: Bondek II 1.0 BMT; studs 19x100 @ 300 single row; edgeform 1.2 BMT, height = slab thickness. `geometry.py` fills their `mto` override (`measure`: deck m2, studs pcs, edgeform m), so they stay out of the steel kg (header card and MTO).
- **Handrail:** flag top rails `rail: "top"` (the page shows kg/m run on a handrail selection; the build stops without it). Grating parts get `mto: {kind: "area", kgm: <kg/m2>, wid: ...}`.
- **Outside model** (IFC, other artifact, HTML): ask whether to break it into selectable parts or keep one reference object.
- **Connections:** welded = zero gap; bolted = a sensible bolted connection (plates, bolt sets, holes).
- **Steel never floats.** A gap drawn between a member and its neighbour (another member, an RC column or wall) is drawing convention: run every end on to what it connects to (column face; axis of the beam it meets, coped; the beam in line, butt joint). Count what is left without a support and write the count into Assumptions.
- **Drawn shapes:** other trades' members are ghosts in their drawn shape (ghost `r` = round column, else box); a CHS is a `CHS` profile, never a square.
- **Cautious:** every joint where a big member meets a small one (deeper than its supporting beam, wider than its column, different sections butting in line; hollow sections and channels too) goes into `cautions` (MTO Summary CAUTIOUS, model Notes) and the member's source line reads CAUTIOUS; hint the count in the reply.
- **Overall structure:** when the drawings show the overall structure (RC, facade, other trades), model it as ghost, one ghost layer per kind (layers with `k: "ghost"`, e.g. "RC (ghost)", "Facade (ghost)"; each ghost names its `layer`), so each can be switched and faded on its own.
- **Marked-up scope:** model only the highlighted scope as steel; neighbours as ghost (transparent, edges, not weighed, not selectable).
- **Ghosts and IFC:** ask before putting ghosts into an IFC.
- **Sequence mode:** only when Yang asks (section 6b).

## 1. Reading drawings
- **Vector PDF fast path** (`generate-model/read_drawing.py`; PyMuPDF `import fitz` is the PDF library here, pypdf and poppler are not installed): `info` (text per sheet + 40 dpi overviews) -> `words` for grid bubbles / level markers -> calibrate each view from one long dimension (mm per pt) -> `members` per view (dashed lines merged, each paired with its mark) -> snap to the dimension chains. Render a crop only to settle a question the vectors cannot answer (what a line is, which way a member faces); never read whole sheets as images. Put a job's reading in `models/<name>/make_spec.py` as numbers, not in throwaway scratch scripts.
- **Cloud session (no PyMuPDF): index first, look second.** Run `python drawings/read_drawings.py jobs/<job> --out jobs/<job>/out/read` and read `index.md`: per sheet the title block (dwg no, rev, status), then every view with its scale, grids, member marks, section sizes, levels and dimensions, plus legends and notes, as text (about 1 k tokens per A1 sheet). Look at each sheet's thumbnail once for the arrangement, then only at crops: `python drawings/crop.py jobs/<job>/out/read --view <id>` (or `--find <mark>`, `--box`, `--part tl` for more detail). Never rasterise a whole sheet at high dpi and never dump `pdftotext -layout` (mostly spaces).
- The index is text, not geometry: confirm on a crop which member each mark and dimension belongs to. Repeated views that read the same in the index (same marks, same dimensions): crop one and check the others against it from the index. A sheet flagged `scan_or_outlined_text` has no real text: thumbnail and crops only. A dimension measured from a crop (the script prints mm per pixel) is "scaled off the drawing" and labelled so.
- **Write the reading down** in `jobs/<job>/out/read/reading.json`: sheets read (dwg no, rev, status), grids, levels per tower or frame, members (`ref`, section, qty, view, sheet), assumptions, left out, open questions. Revisions, the MTO agent and the other skills start from this file and re-open a drawing only for what it does not answer. New drawing revision: rerun with `--prev <old sheets.json>` and re-read only the sheets marked new or changed.
- Read every sheet incl. later revisions (a rev02 "for reference" sheet overrides older levels). State which sheet each tower or frame came from.
- Each tower or frame has its own levels; never copy one elevation onto all. No elevation: say so and state the assumption.
- Members drawn as separate pieces stay separate pieces at their own levels.
- Model every plate, stiffener, lug, clevis, bolt (head, shank, nut) and back plate the details show, in the drawn shapes. Undimensioned size: pick a sensible value and list it. Never invent hardware; ask about unclear symbols.
- Keep a **Left out** list while reading (item, reason, sheet), for section 8.
- **GA floor plans (members = marked lines on 1:100 / 1:200 plans): do not write a reader.** Copy `models/sjii/` (read_plans.py = sheet list, mark pattern, line widths, levels, grids; sections.py = schedule -> Consteel; make_spec.py; make_data.py; build.py) and change the numbers. `ga_plan.py` reads the lines and marks, finds the column outlines (round or rectangular), joins every end to its neighbour (`connect`), returns the Cautious joints and adds the bondek package (`bondek`).
- **Trusses drawn as elevations (outlined members):** copy `models/sjii/read_trusses.py` (chord edges and marks per view as numbers; `ga_plan.bands` finds verticals and diagonals from the outlines and each takes its nearest mark) and the truss block of `models/sjii/make_spec.py` (each truss sits on the plan line that names it; top chord pieces join the floor beams before `connect`; webs bear on the chords; diagonals meeting at one node are mitred). Count the truss positions on the plans before estimating: a sheet of six elevations was 29 trusses on SJII.
- Proprietary parts with a photo or sample are modelled to look like the sample.

## 2. Geometry (geometry.py does the cutting; you decide the inputs)
Write `spec.json` (generate repetitive members with a short Python loop): profiles with real Consteel sizes; per member id, Yang tag `t`, `ref`, `prof`, work points `a`/`b`, `up` (depth direction), `rank` (column 0 < chord 1 < vertical/beam 2 < diagonal 3 < bracing 4) and `ends`. The docstring of `geometry.py` lists every option.
1. **Concentric work points:** corner = column x beam centreline; chevron = beam centreline mid-span; X-brace = panel centre; knee without beam = one node on the column centreline; pinned rod = pin centre. Never keep IFC offsets.
2. **Ends:** `auto` bears on every lower-rank member through the node (diagonal at a node = true notch on chord + vertical). Use `far` where a member runs over its host to the outer face (top chord over an end post), `cope` where a beam frames into an I-section web between its flanges, explicit `plane` for plates and corbels, `null` for a free square end.
3. **Gussets (PL20) only where geometry forces a gap:** chevron pairs, braces under a deep beam, top-module channel joints. Never on a side column.
4. Beams web vertical. Struts concentric with the frame they land on, bearing fully on a foot plate sized to the strut (flag if it passes the beam).
5. Fin plates and stiffeners inside the flanges; column ends reach the splice or cap plate.
6. Crossing rods in one plane: lugs where drawn, bow each rod by half a diameter + 0.5 mm at the crossing.
7. When anything moves, move its whole assembly with one transform; split members crossing a kink. Watch mm vs m.

## 3. Verify before every publish
- `build_model.py` validation must pass. Clash check: SAT on the real prisms, report penetrations over 0.5 mm (bolt shank through its plates is allowed). Gaps and overlaps measured on real vertices, never rounded boxes; every connection piece touches what it is joined to; every remaining gap over 0.5 mm is zero or a rule-2.3 gusset.
- Browser checks (`tests/`): `regress.py` against the last published page when the template or data changed; `rules_check.py` and `generate-mto/tests/mto_parity.py` when the template changed. Look at close-up renders of the joints Yang mentions.
- Template changes also need: `tests/ui_check.py` (chips select, Labels, panel on the right at 4 widths), the panel and toolbar order against section 6, hover readouts at a corner, mid-point, face centre and grid point, the selection chain of a typical member, and the Export button itself (download saves, and with a selection it exports only that, e.g. one lift unit); and the interaction checks: pan after each view preset moves the model right, 60 wheel notches keep moving, after a tower chip + zoom-in drag / pan / wheel still move freely, frame time with Grid + Labels on stays near that with both off, sloped measure reads true length, square measure locks to one axis, Ctrl+Z order in measure mode, untick a tower / Labels, grid label never cut by the section.
- Report only failed checks, with numbers. Never say "fixed" without checking.

## 4. Member tags (Yang's scheme, always)
| Tag | Member | Tag | Member |
|---|---|---|---|
| BR | Bracing (incl. inclined struts, tie-rods) | PLT | Plate: stiffener, fin, gusset, end plate, lug, flat bar |
| P | Purlin | TC / BC / W | Truss top chord / bottom chord / web |
| UB | All horizontal beams | GRT | Grating |
| UC | All columns (incl. vertical posts, props) | CHQ | Chequered plate |
| BU | Built-up I beam or column | ST | Stair |
| C | Channel (PFC, TFC) | HR | Handrail, incl. toe board and gate |
| L | Angle | CL | Cat ladder / cage ladder |
| SH / RH / CH | Square / rectangular / circular hollow | | |
- Number marks per distinct original mark (one-to-one map): `t` = Yang tag, `ref` = original tag (none if not on the drawings).
- Other hardware: BOLT, CLV (clevis), JK, WR, SK, TBK, RB; mention them to Yang. Bondek package: BDK, SS (stud), EF (edgeform).
- A bolt part is a set: store `qty_in`, show "Set of n bolt(s) with nuts".

## 5. Grouping (written into the data)
- Levels: Part > Sub-assembly > Assembly > Lift unit > Tower (skip a level that adds nothing).
- Assembly = main member + plates, stubs, lugs and bolts welded or shop-bolted to it, by geometry (plate inside a column -> column; fin plate on a beam web -> beam; rod + 2 clevises + pins; ledger + its bolt sets).
- Sub-assembly = one tag family inside an assembly (e.g. a landing's handrail); not for PLT, BOLT or single members.
- Lift unit = piece as lifted: each tower split into its pre-assembled frames; loose members between frames are "<part id> (single loose piece)". Transfer beam segments go with their frame unless Yang says otherwise (ask).
- Members that sit on a tower (e.g. cross beams resting on a box tower) belong to that tower's lift unit. A truss lift unit is the truss that bears on its corbels or supports, incl. its own end verticals, and nothing that rests on a neighbouring tower.
- Building: every floor level is one group named after the level ("Level 2") with `label: "Level"`, in the lift-unit slot (member assemblies stay inside it); the block is the tower slot.
- Tower = the whole unit. A group's `label` renames its level in the selection chain (the column unit reads "Columns", not "Tower").

## 6. Data contract (what build_model.py packs into the template)
- `meta`: title, card {title, desc (one short line), ref (drawing ref · grade)}, grade, datum_z (FFL), grand_total_label, currency, export_prefix, unit_names.
- `header` (MTO title block), `units` + `unitKeys`, `groups` [{level: sub | asm | lift | tower, name, label?}], `layers` [{k, n, c}] (one per member type, project layers, Ghost), `cats` [{code, title, layers, dwg}] (every layer in one MTO category), `profs` {name: {d, w, t, cat, kgm, m2m, m2m_assumed, src}} from Consteel (m2m computed = assumed), `gx`/`gy` grids with the drawing's names, `ghosts`, `notes`, `left`, `assumptions`, `noteSections`.
- Part: geometry from geometry.py (`ax`, `L`, `kg`, `pr`) + `t`, `ref`, `prof`, `desc`, `grade` (only if not meta.grade), `layer`, `unit`, `lu`, `tw`, `asm`, `sub`, `src`, `grid`, `plate` {L, W, t, tri} for plates, `rail`, `mto` overrides.
- Layers and colours: one layer per member type (Columns, Beams, Ledgers, Bracing + clevises, Stubs + lugs + back plates, Splice + cap + stiffener plates, Base plates, Bolts + nuts, Ghost, plus project layers). A reference structure layer includes what is welded to it (splice rings, fin plates on an arch section go in e.g. "Arch W2 + W1"). Reference sections: W3 red, W2 orange, W1 yellow, M green, E1 cyan, E2 blue, E3 purple; splice rings neutral. Reference objects solid with their real weight; ghosts about 15 % with edges. Ties as wire rope (rope, turnbuckle, shackles, lug) when Yang specifies rope.
- MTO grade: drawing grade when stated; G8.8 bolts; a grade Claude assumed is *S275; proprietary TBC. Unit weights and m2/m only from Consteel (`generate-mto/references/consteel_catalogue.md`, grep it).
- Template behaviour Yang asked for (keep it): tower chips fly to the unit and select it and never lock the camera (orbit, pan and wheel stay free in every view; a wheel notch never shrinks to nothing near a face); Select buttons in a 3 x 2 grid (Show only, Show all, Hide / Select all, Undo, Export) with Export blue; Section as direction chips (Top, Left, Right, Front, Back), then the slider, then Section on / Clear section; label positions never read layout per frame and the hidden-behind-steel test runs only when the camera rests; Grid and Labels toggles in the toolbar; the panel always on the right (narrower on small screens, never below the view); entering Sequence mode opens Select. A page cannot start a skill itself: say so if Yang asks.
- **The MTO format belongs to generate-mto.** The page's Export runs its port (`generate-mto/port/mto_workbook.js`, injected by `build_model.py`; never edit the workbook code in the template). For "the MTO" of a model, `build.py` runs `page_mtospec.js` + `build_mto.py` directly (no agent); the data carries `cautions`, `left`, `decisions`, `assumptions` and the Summary prints them in that order. Unit names show in full (`Truss UB42`), never bare `UB42`, because beam tags use UB.
- **Not in the template yet:** bolt summary table under the Bolts + nuts layer (rows per bolt mark, sub-total per size, total; counts only what is shown), bolt and proprietary `piece` rows in `mtoSpec`, Sequence mode (6b). Add them to the template in the repo the first time a model needs them, run the tests, commit.

## 6b. Sequence mode (only when Yang asks)
- Never edit the original: copy the artifact as "<title> with-sequence".
- "Model" | "Sequence" chips at the end of the toolbar; step bar at the bottom (previous, numbered chips, next, Play/Pause that freezes mid-step, Free camera that never moves the camera).
- Step text in the Select box (title, "Step n / N", text, colour key: Coming off, Crane + boom, Slings, Lever hoist); no overlay card. Highlight what actually moves; merge steps that happen together.
- Rigging: hook straight under the boom tip; boom tip at one height per lift, only the rope pays out; lugs bolted into existing holes where possible. Lever-hoist release: level while held, then tilts about the lug line until the CG hangs under the hook, tag lines level it before landing.
- No clashes ever: boom (r 320 mm), rope and load path (incl. tilt) against all remaining structure and ground, every step on real triangles; search crane positions and tip heights; report minimum clearance per lift. If a lift cannot be done, say so with reasons and alternatives. Removed items stay removed.

## 8. Each revision
1. Read all of Yang's points; ask with options if one is ambiguous.
2. For a defect, find the root cause and say why it happened.
3. Change `spec.json` / data with a Python script (assert every replacement), rebuild with `geometry.py` and `build_model.py`.
4. Run the section 3 checks. Publish to the same artifact URL.
5. Template or script change: commit and push to the repo (message says what and why).
6. Reply short, in Yang's language: result and file links, then only what failed or was not run, and one line of hints (Cautious count, anything he must act on now). **Cautious**, **Left out** (always; each drawn item not modelled with why and sheet, counts or % where many; or exactly "Nothing left out."), **Decisions for you** and **Assumptions to confirm** are written into the MTO Summary and the model Notes in that order, not repeated in the reply. No recap of what changed.
7. Save new standing rules to memory when Yang states them.
