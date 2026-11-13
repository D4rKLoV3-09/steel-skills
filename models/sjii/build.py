#!/usr/bin/env python3
"""SJII: drawings -> model page -> MTO in one command (about 5 minutes). Copy this file for the next plan job.

    python models/sjii/build.py [--read] [--no-clash]

--read      read the PDFs again (only when the drawings or read_plans.py changed; otherwise plan_members.json is used)
--no-clash  skip the SAT clash check (about 2 minutes) while iterating

Writes jobs/SJII/Models Data/ (spec, parts, extra, data), jobs/SJII/Models/SJII_Steel_Model.html and
jobs/SJII/MTO/ (SJII_mtoSpec.json = the page's own mtoSpec, SJII_MTO.xlsx built by build_mto.py), keeps
models/sjii/sjii.data.json.gz, recalculates the MTO with LibreOffice and checks it.
Prints one line per step and, at the end, only the checks that failed.
"""
import gzip
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
HERE, GM, MTO = ROOT / "models/sjii", ROOT / "generate-model", ROOT / "generate-mto"
JOB = ROOT / "jobs/SJII"
D = JOB / "Models Data"
PAGE, SPEC, XLSX = JOB / "Models/SJII_Steel_Model.html", JOB / "MTO/SJII_mtoSpec.json", JOB / "MTO/SJII_MTO.xlsx"
failed = []


def run(label, *cmd, ok=(0,)):
    t = time.time()
    r = subprocess.run([str(c) for c in cmd], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode not in ok:
        sys.exit(f"{label} FAILED\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    out = r.stdout.strip().splitlines()
    print(f"{label}: {out[-1] if out else 'ok'}  ({time.time() - t:.0f} s)")
    return r.stdout


for p in (D, PAGE.parent, XLSX.parent):
    p.mkdir(parents=True, exist_ok=True)
py = sys.executable
if "--read" in sys.argv or not (HERE / "plan_members.json").exists():
    run("read plans", py, HERE / "read_plans.py", HERE / "plan_members.json")
run("spec", py, HERE / "make_spec.py", HERE / "plan_members.json", D / "sjii.spec.json", D / "sjii.extra.json")
run("geometry", py, GM / "geometry.py", D / "sjii.spec.json", D / "sjii.parts.json")
run("data", py, HERE / "make_data.py", D / "sjii.spec.json", D / "sjii.parts.json", D / "sjii.extra.json", D / "sjii.data.json")
(HERE / "sjii.data.json.gz").write_bytes(gzip.compress((D / "sjii.data.json").read_bytes(), mtime=0))
if "--no-clash" not in sys.argv:
    out = run("clash", py, GM / "tests/clash_check.py", D / "sjii.data.json", D / "sjii.spec.json", ok=(0, 1))
    (D / "clash.txt").write_text(out, encoding="utf-8")
    failed += [ln.strip() for ln in out.splitlines() if ("penetrating pairs" in ln and not ln.split(": ")[1].startswith("0 "))
               or ("not touching" in ln and not ln.split(": ")[1].startswith("0 "))]
run("page", py, GM / "build_model.py", D / "sjii.data.json", PAGE)
run("mtoSpec", "node", MTO / "page_mtospec.js", PAGE, D / "sjii.data.json", SPEC)
run("MTO", py, MTO / "build_mto.py", SPEC, XLSX)

# ---- MTO checks: recalculated, no # errors, grand total = model steel ----
calc = Path(tempfile.mkdtemp())
run("recalculate", "soffice", "--headless", "--convert-to", "xlsx", "--outdir", calc, XLSX)
wb = openpyxl.load_workbook(calc / XLSX.name, data_only=True)
errs = [f"{ws.title}!{c.coordinate}" for ws in wb for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("#")]
if errs:
    failed.append(f"MTO: {len(errs)} # errors, first {errs[:5]}")
tonnes = next((v for row in wb.worksheets[0].iter_rows(values_only=True) if any(isinstance(x, str) and "(tonnes)" in x for x in row)
               for v in row if isinstance(v, (int, float))), None)
data = json.loads((D / "sjii.data.json").read_text(encoding="utf-8"))
model_t = sum(p["kg"] for p in data["parts"] if (p.get("mto") or {}).get("kind") != "measure") / 1000
if tonnes is None or abs(tonnes - model_t) > 0.001 * model_t:
    failed.append(f"MTO grand total {tonnes} t differs from the model steel {model_t:,.1f} t")
shutil.rmtree(calc, ignore_errors=True)
print(f"\nSteel {model_t:,.1f} t, {len(data['parts']):,} parts, cautious {len(data.get('cautions', []))} lines -> {XLSX.relative_to(ROOT)}")
print("FAILED CHECKS:\n  " + "\n  ".join(failed) if failed else "All checks passed.")
if "--no-clash" in sys.argv:
    print("Clash check NOT run (--no-clash).")
