# steel-skills

Scripts behind Yang's slimmed Claude skills. Skills: .claude/skills/<name>/SKILL.md, agents: .claude/agents/, rules: CLAUDE.md. The SKILL.md of each skill says when to run what;
the code lives here so it is not re-read on every call. Line endings are CRLF (kept as-is by .gitattributes).

## Setup in a session
    git clone <this repo> && cd steel-skills
    npm install            # three 0.128.0 + exceljs 4.4.0, only for the browser tests
    pip install --break-system-packages numpy openpyxl playwright   # if missing

## generate-model
| File | Job |
|---|---|
| viewer_template.html | Fixed viewer UI (skill section 6). Placeholders @@TITLE@@, @@DATA@@. Never rewrite per job. |
| build_model.py | data.json -> validated gzip+base64 page (bad indices, missing kg/m, HR without top rail, > 16 MB stop it). |
| geometry.py | spec.json -> zero-gap convex prisms (skill section 2): work points; end cuts auto / near / far / web / cope / plane; per-plate copes. |
| mto_workbook.js | ExcelJS port of build_mto.py (already inside the template; source for re-porting). |
| tests/regress.py | old page vs new page: parts, kg, text, MTO spec, console errors, screenshot. |
| tests/ub42_from_old.py | geometry.py regression on UB42 (204 parts within 0.1 mm). |
| tests/rules_check.py | standing rules in the browser: handrail kg/m, dual-tag search, grating / bondek MTO rows. |
| tests/mto_parity.py | page export vs build_mto.py, cell by cell + LibreOffice recalc. |
| tests/fixtures/ub4.data.json | UB4 model data (1,662 parts, 76,650.7 kg): the regression baseline. |

## generate-mto
| File | Job |
|---|---|
| build_mto.py | spec.json -> MTO workbook, columns A-W (painting m2/m + painted area, Run m, Area m2, kg/m run). |
| references/consteel_catalogue.md | Consteel 2025 kg/m and m2/m tables: grep for the section, never read whole. |
| tests/test_columns.py | painting, handrail kg/m run, grating m2, bondek m2, edgeform m vs hand-worked values. |
