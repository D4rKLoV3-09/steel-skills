#!/usr/bin/env python3
"""data.json -> one self-contained three.js viewer page.

    python build_model.py DATA.json OUT.html [--template viewer_template.html]

DATA.json is the model data block (parts with convex prisms, groups, layers, units, ...).
The fixed viewer UI lives in viewer_template.html; the MTO export code is injected from
generate-mto/port/mto_workbook.js (the MTO agent owns the workbook format); project text comes from data["meta"],
data["header"] and data["noteSections"]. Nothing project-specific is hard-coded in the template.
"""
import argparse
import base64
import gzip
import json
import pathlib
import sys

REQUIRED = ["header", "meta", "parts", "groups", "layers", "units", "unitKeys", "ghosts",
            "gx", "gy", "profs", "cats", "notes", "left", "assumptions", "noteSections"]
META_KEYS = ["title", "grand_total_label", "currency", "export_prefix"]
PART_KEYS = ["t", "ax", "prof", "layer", "unit", "lu", "tw", "asm", "sub", "L", "kg", "src", "grid", "desc", "plate", "pr"]
MAX_PAGE_MB = 16


def validate(d):
    """Return a list of problems. Empty list = safe to build."""
    errs = []
    missing = [k for k in REQUIRED if k not in d]
    if missing:
        return [f"missing top-level keys: {missing}"]
    errs += [f"meta.{k} missing" for k in META_KEYS if k not in d["meta"]]
    card = d["meta"].get("card", {})
    errs += [f"meta.card.{k} missing (project header card)" for k in ("title", "desc", "ref") if not card.get(k)]
    hr = [p for p in d["parts"] if p.get("t", "").upper().startswith("HR")]
    if hr and not any(p.get("rail") == "top" for p in hr):
        errs.append("handrail parts (HR) but no top rail flagged rail='top': kg/m run cannot be shown")
    if len(d["units"]) != len(d["unitKeys"]):
        errs.append(f"units ({len(d['units'])}) and unitKeys ({len(d['unitKeys'])}) differ in length")
    n_layer, n_unit, n_group = len(d["layers"]), len(d["units"]), len(d["groups"])
    ghost_layers = {i for i, l in enumerate(d["layers"]) if l.get("k") == "ghost"}
    for i, g in enumerate(d["ghosts"]):
        if "layer" in g and g["layer"] not in ghost_layers:
            errs.append(f"ghost[{i}]: layer {g['layer']} is not a ghost layer (k='ghost')")
    if d["ghosts"] and not ghost_layers:
        errs.append("ghosts present but no layer with k='ghost'")
    bdk = {p["layer"] for p in d["parts"] if (p.get("mto") or {}).get("kind") == "measure" and p.get("t", "")[:2] in ("BD", "SS", "EF")}
    if len(bdk) > 1:
        errs.append(f"bondek, studs and edgeform must share ONE layer (found layers {sorted(bdk)})")
    errs += [f"layer {li} ({d['layers'][li]['n']}): the bondek package layer must be hidden by default (off: true)"
             for li in bdk if 0 <= li < n_layer and not d["layers"][li].get("off")]
    covered = {li for c in d["cats"] for li in c["layers"]}
    for i, p in enumerate(d["parts"]):
        tag = f"part[{i}] {p.get('t', '?')}"
        absent = [k for k in PART_KEYS if k not in p]
        if absent:
            errs.append(f"{tag}: missing {absent}")
            continue
        if not 0 <= p["layer"] < n_layer:
            errs.append(f"{tag}: layer {p['layer']} out of range")
        elif p["layer"] not in covered:
            errs.append(f"{tag}: layer {p['layer']} is in no MTO category (export would fail)")
        if not 0 <= p["unit"] < n_unit:
            errs.append(f"{tag}: unit {p['unit']} out of range")
        for g in ("lu", "tw", "asm"):
            if not 0 <= p[g] < n_group:
                errs.append(f"{tag}: group index {g}={p[g]} out of range")
        if p["sub"] != -1 and not 0 <= p["sub"] < n_group:
            errs.append(f"{tag}: sub={p['sub']} out of range")
        if d["layers"][p["layer"]].get("k") == "ghost" if 0 <= p["layer"] < n_layer else False:
            errs.append(f"{tag}: steel part on a ghost layer")
        measured = (p.get("mto") or {}).get("kind") == "measure"       # bondek package: counted, no unit weight needed
        if p["plate"] is None and not measured and p["prof"] not in d["profs"]:
            errs.append(f"{tag}: section '{p['prof']}' not in profs (no unit weight)")
        if not p["pr"]:
            errs.append(f"{tag}: no geometry")
        for prism in p["pr"]:
            for face in prism:
                if len(face) < 3 or any(len(v) != 3 for v in face):
                    errs.append(f"{tag}: malformed face")
                    break
        if len(errs) > 40:
            errs.append("... stopped after 40 problems")
            break
    return errs


def build(data_path, out_path, template_path, port_path):
    d = json.loads(pathlib.Path(data_path).read_text(encoding="utf-8"))
    errs = validate(d)
    if errs:
        print("DATA INVALID:", *errs, sep="\n  ", file=sys.stderr)
        return 1
    raw = json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    b64 = base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode("ascii")
    tpl = pathlib.Path(template_path).read_text(encoding="utf-8")
    assert tpl.count("@@DATA@@") == 1 and tpl.count("@@TITLE@@") == 1 and tpl.count("/*@@MTO_PORT@@*/") == 1, "template placeholders damaged"
    port = pathlib.Path(port_path).read_text(encoding="utf-8")     # the MTO format belongs to generate-mto
    assert "function buildWorkbook(spec)" in port, f"{port_path} is not the MTO workbook port"
    html = tpl.replace("@@TITLE@@", d["meta"]["title"]).replace("/*@@MTO_PORT@@*/", port).replace("@@DATA@@", b64)
    size_mb = len(html.encode("utf-8")) / 1e6
    pathlib.Path(out_path).write_text(html, encoding="utf-8", newline="")
    kg = sum(p["kg"] for p in d["parts"])
    print(f"built {out_path}: {len(d['parts'])} parts, {kg:,.1f} kg, {size_mb:.2f} MB (limit {MAX_PAGE_MB} MB)")
    if size_mb > MAX_PAGE_MB:
        print("PAGE TOO LARGE for an artifact: round coordinates or drop detail", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    here = pathlib.Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data")
    ap.add_argument("out")
    ap.add_argument("--template", default=str(here / "viewer_template.html"))
    ap.add_argument("--mto-port", default=str(here.parent / "generate-mto" / "port" / "mto_workbook.js"),
                    help="ExcelJS port of build_mto.py, owned by generate-mto")
    a = ap.parse_args()
    sys.exit(build(a.data, a.out, a.template, a.mto_port))
