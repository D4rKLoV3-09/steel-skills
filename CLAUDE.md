# steel-skills: Yang's steel agents

Yang (Steel Hub Engineering, Johor) runs his steel work here: 3D models (`generate-model` skill) and material
take-offs (`generate-mto` agent). Reply in Chinese unless asked otherwise, pyramid form (conclusion first),
short and actionable. When a choice is genuinely Yang's, give 2-3 options instead of guessing.

## Where things are
- `.claude/skills/generate-model/SKILL.md`: 3D model rules. Code: `generate-model/` (viewer_template.html, geometry.py, build_model.py, tests/).
- `.claude/skills/generate-mto/SKILL.md` + `.claude/agents/generate-mto.md`: the MTO agent. Code: `generate-mto/` (build_mto.py, port/, references/, tests/).
- `models/<name>/`: a model's data (`<name>.data.json`) and its revision scripts. Rebuild a page from here.
- `jobs/<job>/`: Yang's drawings for a job (not uploaded to GitHub). Write results to `jobs/<job>/out/`.

## Job routine
1. Read every drawing in `jobs/<job>/`: text index first (`drawings/read_drawings.py`), then crops (`drawings/crop.py`), and record the reading in `jobs/<job>/out/read/reading.json` so nobody reads the same sheet twice. Ask only what blocks the work; otherwise decide, label it, go on.
2. Model asked: spec.json -> `geometry.py` -> data.json -> `build_model.py` -> `jobs/<job>/out/<name>.html`; run the skill's checks; keep the data in `models/<name>/`.
3. MTO asked (or "model + MTO"): hand the spec (the model page's `mtoSpec`, or rows read from the drawings) to the **generate-mto** agent; it returns `jobs/<job>/out/<Project>_MTO.xlsx` and a report.
4. Reply: result first, then **Decisions for you**, **Assumptions to confirm**, **Left out** (or "Nothing left out.").
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
- Search for an existing library before writing non-trivial custom code.
- Files for Windows use CRLF line endings (always for .bat).
