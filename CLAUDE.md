# steel-skills: Yang's steel agents

Yang (Steel Hub Engineering, Johor) runs his steel work here: 3D models (`generate-model` skill) and material
take-offs (`generate-mto` agent). Reply in the language Yang writes in (English to English, Chinese to Chinese),
pyramid form (conclusion first),
short and actionable. When a choice is genuinely Yang's, give 2-3 options instead of guessing.

## Where things are
- `.claude/skills/generate-model/SKILL.md`: 3D model rules. Code: `generate-model/` (viewer_template.html, geometry.py, build_model.py, ga_plan.py = GA floor plans -> connected framing, tests/).
- `.claude/skills/generate-mto/SKILL.md` + `.claude/agents/generate-mto.md`: the MTO agent. Code: `generate-mto/` (build_mto.py, port/, references/, tests/).
- `models/<name>/`: a model's data (`<name>.data.json`) and its scripts; `build.py` there runs the whole chain (drawings -> page -> MTO -> checks) in one command. Rebuild from here.
- `jobs/<job>/`: Yang's drawings for a job (not uploaded to GitHub). Write results to `jobs/<job>/out/`.

## Job routine
1. Read every drawing in `jobs/<job>/` with the readers, not by eye (PC: `generate-model/read_drawing.py`; claude.ai cloud session: `drawings/read_drawings.py` + `drawings/crop.py`), and record the reading in `jobs/<job>/out/read/reading.json` so nobody reads the same sheet twice. Ask only what blocks the work; otherwise decide, label it, go on.
2. Model asked: `python models/<name>/build.py` (spec -> `geometry.py` -> data -> checks -> `build_model.py` -> page). New job: copy the scripts of the closest existing model (floor plans: `models/sjii/`) and change the numbers; never write a reader or a viewer again.
3. MTO asked: from a model, `build.py` already makes it (`generate-mto/page_mtospec.js` -> `build_mto.py`, no agent). Without a model (rows from drawings, IFC / Tekla report, previous MTO): the **generate-mto** agent.
4. Reply: result and file links first, then only what failed or needs Yang now, plus one line of hints (e.g. how many Cautious joints). The lists go into the MTO Summary and the model Notes in this order, not into the reply: **Cautious**, **Left out** (or "Nothing left out."), **Decisions for you**, **Assumptions to confirm**. No check results unless a check failed or was not run.
5. Commit code or model-data changes with a clear message; push when Yang says so.

## Standing rules (Yang)
- Member tags: always Yang's tags (UB, UC, BR, TC/BC/W, P, PLT, HR, GRT, ...); the drawing's own mark kept as `ref` / "Ref ..." and searchable. Unit names in full ("Truss UB42"), never bare "UB42".
- Unit weights, sizes and m2/m only from the Consteel 2025 catalogue (`generate-mto/references/consteel_catalogue.md`, grep it).
- A steel grade Claude assumes = `*S275`.
- Bondek is Yang's scope and always comes with shear studs and edgeform; a slab on his steel = bondek even if not drawn (defaults: Bondek II 1.0 BMT, studs 19x100 @ 300, edgeform 1.2 BMT, ASSUMED). In the MTO its own category in m2 / pcs / m, outside the steel tonnage.
- Every MTO carries painting m2 and, only where the drawings show them, handrail m run + kg/m run, grating m2, bondek m2, edgeform m run. Nothing is shown for an item that is not on the drawings.
- Bondek, shear studs and edgeform: one layer, hidden by default, always the standard models in `geometry.py`.
- Buildings: every floor level is one group labelled "Level". Overall structure on the drawings (RC, facade, others) = ghost, one ghost layer per kind.
- Selecting a handrail assembly in a model shows its kg/m run.
- Ghost structures: ask before putting them into an IFC.
- Erection sequence on a model: never edit the original; copy it as "<title> with-sequence".
- Steel never floats: a gap drawn between a member and its neighbour (steel or RC) is drawing convention. Run every end on to what it connects to, zero gap; anything left without a support is counted and reported.
- Other trades' members (RC columns, walls) are shown in their drawn shape: a round column is round, never a box.
- **Cautious**: wherever a big member meets a small one (deeper than its supporting beam, wider than its column, different sections butting in line; hollow sections and channels too), hint Yang in the reply and list it in the MTO Summary under CAUTIOUS, above Left out.
- Speed: a job is scripts, not chat. One `build.py` per model; test into the scratch folder; print counts instead of reading JSON; no agent for what a script does; fix the shared script, not the output.
- Search for an existing library before writing non-trivial custom code.
- Files for Windows use CRLF line endings (always for .bat).
