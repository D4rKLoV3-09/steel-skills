#!/usr/bin/env python3
"""Vector PDF drawings -> a small text index, so sheets are read as text first and looked at only in crops.

    python read_drawings.py PDF [PDF ...] --out jobs/<job>/out/read
    python read_drawings.py jobs/<job> --out jobs/<job>/out/read        (every PDF in the folder)
    python read_drawings.py ... --prev OLD/sheets.json                  (marks sheets whose text changed)

Writes into --out:
  index.md       read this first (about 1-2 k tokens per A1 sheet): title block, then every view with its
                 scale, grids, member marks, section sizes, levels, dimensions and other text; legends and notes.
  sheets.json    the same with coordinates (points, as displayed) for crop.py and later scripts. Do not read it.
  thumbs/<sheet>.png   one low-resolution overview per sheet (look at it once to see the arrangement).

Then look at details with crop.py (by view id, by text, or by box). Never rasterise a whole sheet at high dpi.

How views are found: the vector linework and text are clustered by white space; a cluster is named by the view
title inside it (the line above a scale such as "1 : 50"). Clusters holding several titles are cut between them.
A sheet with fewer than MIN_WORDS words is flagged "scan_or_outlined_text": its text is not real text, so use
the thumbnail and crops only (or OCR).
Needs: pdfplumber, opencv (cv2), numpy, poppler (pdftotext, pdftoppm).
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import cv2
import numpy as np
import pdfplumber

CELL = 4.0            # pt per mask cell
GAP = 13.0            # pt: linework closer than 2 x GAP belongs to the same view
MIN_WORDS = 15
THUMB_PX = 1300       # long side of the overview image

SCALE_RE = re.compile(r"^(?:SCALE\s*)?1\s*:\s*(\d+(?:\.\d+)?)$|^N\.?T\.?S\.?$", re.I)
SECTION_RE = re.compile(
    r"\b(?:UB|UC|UKB|UKC|PFC|TFC|UPN|IPE|HE[AB]?|SHS|RHS|CHS|EA|UA|FB|PL|PLT|L|C|Z)\s?\d+(?:\.\d+)?"
    r"(?:\s?[xX×]\s?\d+(?:\.\d+)?){0,3}(?:\s?(?:kg/m|THK|mm))?", re.I)
LEVEL_RE = re.compile(r"^[+-]?\d{1,3}\.\d{2,3}$")
LEVEL_WORDS = ("TOC", "TOS", "TOG", "FFL", "SFL", "EL", "RL", "BOS", "SSL", "LEVEL", "LVL", "T.O.S", "T.O.C")
DIM_RE = re.compile(r"^\d{2,6}$|^\d+\s*(?:x|X|@|c/c|TYP).*$")
MARK_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9]+(?:[-_/.][A-Za-z0-9]+)+$")
GRID_RE = re.compile(r"^[A-Z]{1,2}\d{0,3}'?$|^\d{1,3}[A-Z]?'?$")
TB_LABELS = ("DRAWING NO", "DWG NO", "DRAWING TITLE", "PROJECT TITLE", "REV", "SCALE", "DATE", "DRAWN", "CHECKED",
             "JOB NO", "SHEET", "PROJECT PHASE", "STATUS")


# ---------------- text ----------------
def text_lines(pdf, page_no):
    """Lines of text with boxes in displayed coordinates (pdftotext handles rotated pages and vertical text)."""
    xml = subprocess.run(["pdftotext", "-bbox-layout", "-f", str(page_no), "-l", str(page_no), str(pdf), "-"],
                         capture_output=True, text=True, check=True).stdout
    xml = re.sub(r"<!DOCTYPE[^>]*>", "", xml).replace('xmlns="http://www.w3.org/1999/xhtml"', "")
    root = ET.fromstring(xml)
    page = root.find(".//page")
    out = []
    for bi, block in enumerate(page.iter("block")):
        for line in block.iter("line"):
            words = [w.text or "" for w in line.iter("word")]
            if not words:
                continue
            box = [float(line.get(k)) for k in ("xMin", "yMin", "xMax", "yMax")]
            out.append({"t": " ".join(words).strip(), "box": box, "block": bi})
    return out


def merge_slanted(lines, page):
    """Text written along a sloping member (a brace mark) reaches pdftotext as fragments: rebuild it from the
    characters, which carry their angle, and drop the fragments."""
    import math
    runs, cur = [], None
    for c in page.chars:
        m = c["matrix"]
        ang = round(math.degrees(math.atan2(m[1], m[0])))
        if ang % 90 == 0:
            cur = None
            continue
        cx, cy = (c["x0"] + c["x1"]) / 2, (c["top"] + c["bottom"]) / 2
        if cur and cur["ang"] == ang and math.hypot(cx - cur["last"][0], cy - cur["last"][1]) < 2.2 * c["size"]:
            if math.hypot(cx - cur["last"][0], cy - cur["last"][1]) > 0.95 * c["size"]:
                cur["t"] += " "
            cur["t"] += c["text"]
            cur["pts"].append((cx, cy))
        else:
            cur = {"ang": ang, "t": c["text"], "pts": [(cx, cy)]}
            runs.append(cur)
        cur["last"] = (cx, cy)
    runs = [r for r in runs if r["t"].strip()]
    if not runs:
        return lines
    pts = [p for r in runs for p in r["pts"]]
    keep = []
    for l in lines:
        b = l["box"]
        hit = sum(1 for x, y in pts if b[0] - 2 <= x <= b[2] + 2 and b[1] - 2 <= y <= b[3] + 2)
        if hit < max(1, 0.6 * len(l["t"].replace(" ", ""))):
            keep.append(l)
    for r in runs:
        xs, ys = [p[0] for p in r["pts"]], [p[1] for p in r["pts"]]
        keep.append({"t": re.sub(r"\s+", " ", r["t"]).strip(), "box": [min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3],
                     "block": -1, "slant": r["ang"]})
    return keep


# ---------------- linework ----------------
def segments(page):
    segs = []
    for l in page.lines:
        segs.append((l["x0"], l["top"], l["x1"], l["bottom"]))
    for r in page.rects:
        x0, y0, x1, y1 = r["x0"], r["top"], r["x1"], r["bottom"]
        segs += [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]
    for c in page.curves:
        pts = c.get("pts") or []
        for a, b in zip(pts, pts[1:]):
            segs.append((a[0], a[1], b[0], b[1]))
    return segs


def frame_and_titleblock(W, H, segs):
    """Sheet frame = the long lines; title block = the narrow strip the frame cuts off at the right or bottom."""
    vs = sorted({round(s[0]) for s in segs if abs(s[0] - s[2]) < 1 and abs(s[1] - s[3]) > 0.8 * H})
    hs = sorted({round(s[1]) for s in segs if abs(s[1] - s[3]) < 1 and abs(s[0] - s[2]) > 0.8 * W})
    tb = None
    if len(vs) >= 2:
        inner = [x for x in vs if 0.6 * W < x < vs[-1] - 0.04 * W]
        if inner:
            tb = [inner[-1], 0, W, H]
    if tb is None and len(hs) >= 2:
        inner = [y for y in hs if 0.7 * H < y < hs[-1] - 0.03 * H]
        if inner:
            tb = [0, inner[-1], W, H]
    return vs, hs, tb


def inside(box, region, tol=1.0):
    return region is not None and box[0] >= region[0] - tol and box[1] >= region[1] - tol and \
        box[2] <= region[2] + tol and box[3] <= region[3] + tol


# ---------------- views ----------------
def find_titles(lines):
    """A view title is the text line just above a scale line ("1 : 50") and left-aligned with it."""
    titles = []
    for s in lines:
        m = SCALE_RE.match(s["t"])
        if not m:
            continue
        sx0, sy0 = s["box"][0], s["box"][1]
        best = None
        for l in lines:
            if l is s or SCALE_RE.match(l["t"]) or len(l["t"]) < 3:
                continue
            dy = sy0 - l["box"][3]
            if -3 <= dy <= 30 and abs(l["box"][0] - sx0) <= 25 and (best is None or dy < best[0]):
                best = (dy, l)
        if not best:
            continue
        t = best[1]
        # view number: a short token just left of the title (the bubble)
        no = None
        for l in lines:
            if len(l["t"]) <= 4 and 0 < t["box"][0] - l["box"][2] < 60 and \
                    l["box"][1] < s["box"][3] + 4 and l["box"][3] > t["box"][1] - 14:
                no = l["t"]
        title = t["t"]
        m2 = re.match(r"^(\d{1,2}[A-Z]?|[A-Z]\d?)\s+(.{3,})$", title)
        if no is None and m2:
            no, title = m2.group(1), m2.group(2)
        elif no is not None and m2 and m2.group(1) == no:
            title = m2.group(2)
        titles.append({"no": no, "title": title, "scale": s["t"].replace(" ", ""),
                       "box": [min(t["box"][0], s["box"][0]) - (40 if no else 0), t["box"][1],
                               max(t["box"][2], s["box"][2]), s["box"][3]]})
    return titles


def cluster(W, H, segs, lines, skip_regions):
    gw, gh = int(W / CELL) + 2, int(H / CELL) + 2
    mask = np.zeros((gh, gw), np.uint8)
    for x0, y0, x1, y1 in segs:
        if (abs(x0 - x1) < 1 and abs(y0 - y1) > 0.8 * H) or (abs(y0 - y1) < 1 and abs(x0 - x1) > 0.8 * W):
            continue                                              # sheet frame
        if any(inside([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)], r) for r in skip_regions):
            continue
        cv2.line(mask, (int(x0 / CELL), int(y0 / CELL)), (int(x1 / CELL), int(y1 / CELL)), 255, 1)
    for l in lines:
        b = l["box"]
        if any(inside(b, r) for r in skip_regions):
            continue
        cv2.rectangle(mask, (int(b[0] / CELL), int(b[1] / CELL)), (int(b[2] / CELL), int(b[3] / CELL)), 255, -1)
    k = int(GAP / CELL) * 2 + 1
    fat = cv2.dilate(mask, np.ones((k, k), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fat, 8)
    boxes = []
    for i in range(1, n):
        x, y, w, h, _ = stats[i]
        pad = GAP - CELL
        boxes.append([max(0, x * CELL + pad), max(0, y * CELL + pad), min(W, (x + w) * CELL - pad), min(H, (y + h) * CELL - pad)])
    return boxes


def split_by_titles(box, titles):
    """Titles sit under their view: cut a multi-title cluster under each title (stacked) or left of it (side by side)."""
    if len(titles) <= 1:
        return [(box, titles[0] if titles else None)]
    ts = sorted(titles, key=lambda t: (t["box"][1], t["box"][0]))
    stacked = all(b["box"][1] > a["box"][3] for a, b in zip(ts, ts[1:]))
    out = []
    if stacked:
        top = box[1]
        for i, t in enumerate(ts):
            bot = box[3] if i == len(ts) - 1 else t["box"][3] + 6
            out.append(([box[0], top, box[2], bot], t))
            top = bot
    else:
        ts = sorted(titles, key=lambda t: t["box"][0])
        left = box[0]
        for i, t in enumerate(ts):
            right = box[2] if i == len(ts) - 1 else ts[i + 1]["box"][0] - 6
            out.append(([left, box[1], right, box[3]], t))
            left = right
    return out


def centre_in(b, box):
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return box[0] <= cx <= box[2] and box[1] <= cy <= box[3]


def classify(texts, titles_text):
    """Group a view's text lines. Counts kept ("x3") so a quantity can be read without looking."""
    cnt = {}
    for t in texts:
        cnt[t] = cnt.get(t, 0) + 1
    g = {"sections": [], "marks": [], "levels": [], "grids": [], "dims": [], "refs": [], "text": []}
    for t, n in cnt.items():
        s = f"{t} x{n}" if n > 1 else t
        up = t.upper()
        if t in titles_text or SCALE_RE.match(t):
            continue
        if SECTION_RE.search(t) and not MARK_RE.match(t):
            g["sections"].append(s)
        elif LEVEL_RE.match(t) or (any(up.startswith(w) for w in LEVEL_WORDS) and re.search(r"\d", t)):
            g["levels"].append(s)
        elif DIM_RE.match(t):
            g["dims"].append(s)
        elif MARK_RE.match(t):
            (g["refs"] if re.search(r"-(?:DET|GA|LAY|SEC|DWG|SSTEL|STR)\b|-\d{3,}$", up) and len(t) > 14 else g["marks"]).append(s)
        elif GRID_RE.match(t):
            g["grids"].append(s)
        else:
            g["text"].append(s)
    return {k: v for k, v in g.items() if v}


# ---------------- title block ----------------
def title_block(lines, tb, W, H):
    tl = [l for l in lines if inside(l["box"], tb)] if tb else []
    if not tl:                                    # no strip found: take text near the usual labels
        keys = [l for l in lines if any(k in l["t"].upper() for k in ("DRAWING NO", "DWG NO", "DRAWING TITLE"))]
        if keys:
            x0 = min(k["box"][0] for k in keys) - 20
            tl = [l for l in lines if l["box"][0] >= x0]
    tl.sort(key=lambda l: (round(l["box"][1] / 6), l["box"][0]))
    rows, cur, cy = [], [], None
    for l in tl:
        if cy is None or abs(l["box"][1] - cy) > 6:
            if cur:
                rows.append(cur)
            cur, cy = [], l["box"][1]
        cur.append(l)
    if cur:
        rows.append(cur)
    text = [" | ".join(l["t"] for l in sorted(r, key=lambda l: l["box"][0])) for r in rows]
    fields = {}

    def is_label(t):
        up = t.upper().strip()
        return up.endswith(":") or any(up.startswith(k) for k in TB_LABELS)

    anchor = next((l for l in tl if l["t"].upper().startswith(("DRAWING NO", "DWG NO"))), None)

    def value_after(label):
        """Value right of / below a label. Several labels with the same name (REV, DATE also head the revision
        table): take the one nearest the drawing number."""
        occ = [l for l in tl if l["t"].upper().startswith(label)]
        if not occ:
            return None
        if anchor:
            occ.sort(key=lambda l: abs(l["box"][0] - anchor["box"][0]) + abs(l["box"][1] - anchor["box"][1]))
        l = occ[0]
        rest = l["t"][len(label):].strip(" :.")
        if rest.upper().startswith("NO"):
            rest = rest[2:].strip(" :.")
        if rest:
            return rest
        best = None
        for o in tl:
            if o is l or is_label(o["t"]) or o["box"][2] <= l["box"][0] or o["box"][3] <= l["box"][1] + 1:
                continue
            dx, dy = max(0.0, o["box"][0] - l["box"][2]), max(0.0, o["box"][1] - l["box"][3])
            d = dx + 2 * dy
            if d < 160 and (best is None or d < best[0]):
                best = (d, o["t"])
        return best and best[1]

    for key, label in (("dwg_no", "DRAWING NO"), ("dwg_no", "DWG NO"), ("rev", "REV"), ("scale", "SCALE"),
                       ("date", "DATE"), ("status", "PROJECT PHASE"), ("status", "STATUS"), ("job_no", "JOB NO"),
                       ("sheet", "SHEET")):
        if key not in fields:
            v = value_after(label)
            if v:
                fields[key] = v
    # drawing title = the lines between "DRAWING TITLE" and the next label row
    for i, r in enumerate(rows):
        if any(l["t"].upper().startswith("DRAWING TITLE") for l in r):
            ttl = []
            for r2 in rows[i + 1:]:
                if any(any(l["t"].upper().startswith(k) for k in TB_LABELS + ("DESIGNED",)) for l in r2):
                    break
                ttl.append(" ".join(l["t"] for l in r2))
            if ttl:
                fields["title"] = " / ".join(ttl)
    return fields, text


# ---------------- one page ----------------
def read_page(pdf, page_no, page):
    W, H = float(page.width), float(page.height)          # displayed size (rotation applied)
    lines = merge_slanted(text_lines(pdf, page_no), page)
    segs = segments(page)
    _, _, tb = frame_and_titleblock(W, H, segs)
    fields, tb_text = title_block(lines, tb, W, H)
    body = [l for l in lines if not inside(l["box"], tb)]
    titles = find_titles(body)
    views = []
    for box in cluster(W, H, segs, body, [tb] if tb else []):
        inside_titles = [t for t in titles if centre_in(t["box"], box)]
        for vbox, t in split_by_titles(box, inside_titles):
            texts = [l for l in body if centre_in(l["box"], vbox)]
            if not texts and (vbox[2] - vbox[0]) * (vbox[3] - vbox[1]) < 0.002 * W * H:
                continue                                   # stray mark without text
            views.append({"box": [round(v, 1) for v in vbox], "title": t, "lines": texts})
    views.sort(key=lambda v: (v["title"] is None, round(v["box"][0] / (W / 6)), v["box"][1]))
    out, used = [], set()
    for i, v in enumerate(views):
        t = v["title"]
        texts = [l["t"] for l in v["lines"]]
        if t:
            vid = t["no"] or f"V{i + 1}"
            name, scale = t["title"], t["scale"]
        else:
            first = sorted(v["lines"], key=lambda l: (l["box"][1], l["box"][0]))
            name = first[0]["t"] if first else "(linework only)"
            vid, scale = f"X{i + 1}", None
        while vid in used:
            vid += "'"
        used.add(vid)
        tt = {t["title"], f'{t["no"]} {t["title"]}', t["no"]} if t else set()
        entry = {"id": vid, "name": name, "scale": scale, "box": v["box"], "titled": bool(t)}
        if t:
            entry["items"] = classify(texts, tt)
        else:                                               # legend, notes, schedule: keep the reading order
            rows = sorted(v["lines"], key=lambda l: (round(l["box"][1] / 5), l["box"][0]))
            merged, cy = [], None
            for l in rows:
                if cy is not None and abs(l["box"][1] - cy) <= 5:
                    merged[-1] += " | " + l["t"]
                else:
                    merged.append(l["t"])
                cy = l["box"][1]
            entry["rows"] = merged
        entry["words"] = [{"t": l["t"], "box": [round(b, 1) for b in l["box"]]} for l in v["lines"]]
        out.append(entry)
    words = sum(len(l["t"].split()) for l in lines)
    digest = hashlib.sha1("\n".join(sorted(l["t"] for l in lines)).encode()).hexdigest()[:12]
    return {"page": page_no, "size_pt": [W, H], "titleblock": fields, "titleblock_text": tb_text,
            "titleblock_box": tb, "views": out, "words": words, "hash": digest,
            "flag": None if words >= MIN_WORDS else "scan_or_outlined_text"}


# ---------------- output ----------------
def paper(W, H):
    mm = sorted((W * 25.4 / 72, H * 25.4 / 72))
    for name, (a, b) in {"A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297)}.items():
        if abs(mm[0] - a) < 8 and abs(mm[1] - b) < 8:
            return name
    return f"{mm[1]:.0f}x{mm[0]:.0f} mm"


def write_index(sheets, out):
    L = ["# Drawing index (text only: confirm geometry on crops, `crop.py <pdf> --view <id>`)", ""]
    L.append("| Sheet | Dwg no | Rev | Status | Title | Views | Changed |")
    L.append("|---|---|---|---|---|---|---|")
    for s in sheets:
        f = s["titleblock"]
        L.append(f'| {s["sheet"]} | {f.get("dwg_no", "?")} | {f.get("rev", "?")} | {f.get("status", "?")} | '
                 f'{f.get("title", "?")} | {sum(v["titled"] for v in s["views"])} | {s.get("changed", "")} |')
    for s in sheets:
        f = s["titleblock"]
        L += ["", f'## {s["sheet"]}  ({s["file"]} p{s["page"]}, {paper(*s["size_pt"])})']
        if s["flag"]:
            L.append(f'**{s["flag"]}: only {s["words"]} words of real text. Use the thumbnail and crops.**')
        L.append("Title block: " + "; ".join(f"{k}={v}" for k, v in f.items()))
        vals = {str(v) for v in f.values()} | set(str(f.get("title", "")).split(" / "))
        rest = [t for t in s["titleblock_text"] if t not in vals and not t.rstrip().endswith(":")
                and not all(p.strip() in vals or p.strip().endswith(":") for p in t.split("|"))]
        if rest:
            L.append("Other title-block text: " + " ¦ ".join(rest)[:600])
        for v in s["views"]:
            head = f'### {v["id"]}: {v["name"]}' + (f' ({v["scale"]})' if v["scale"] else "")
            L.append(head)
            if "rows" in v:
                L += [f"  {r}" for r in v["rows"]]
            else:
                for k, vals in v["items"].items():
                    L.append(f"  {k}: " + ", ".join(vals))
    (out / "index.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="PDF files or a folder of PDFs")
    ap.add_argument("--out", required=True)
    ap.add_argument("--prev", help="sheets.json of the previous revision: marks new / changed / same per sheet")
    ap.add_argument("--no-thumbs", action="store_true")
    a = ap.parse_args()
    pdfs = []
    for i in a.inputs:
        p = pathlib.Path(i)
        pdfs += sorted(p.rglob("*.pdf")) if p.is_dir() else [p]
    out = pathlib.Path(a.out)
    (out / "thumbs").mkdir(parents=True, exist_ok=True)
    prev = {}
    if a.prev:
        for s in json.loads(pathlib.Path(a.prev).read_text(encoding="utf-8"))["sheets"]:
            prev[s["titleblock"].get("dwg_no") or s["sheet"]] = s
    sheets = []
    for pdf in pdfs:
        with pdfplumber.open(pdf) as doc:
            for n, page in enumerate(doc.pages, 1):
                s = read_page(pdf, n, page)
                s["file"] = str(pdf)
                base = re.sub(r"[^A-Za-z0-9_.-]+", "_", s["titleblock"].get("dwg_no") or pdf.stem)
                s["sheet"] = base if len(doc.pages) == 1 or s["titleblock"].get("dwg_no") else f"{base}_p{n}"
                if a.prev:
                    old = prev.get(s["titleblock"].get("dwg_no") or s["sheet"])
                    s["changed"] = "new" if old is None else ("same" if old["hash"] == s["hash"] else
                                                               f'changed (was rev {old["titleblock"].get("rev", "?")})')
                if not a.no_thumbs:
                    W, H = s["size_pt"]
                    dpi = max(20, int(THUMB_PX / max(W, H) * 72))
                    stem = out / "thumbs" / s["sheet"]
                    subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(n), "-l", str(n), "-singlefile", "-png",
                                    str(pdf), str(stem)], check=True)
                    s["thumb"] = str(stem) + ".png"
                sheets.append(s)
    (out / "sheets.json").write_text(json.dumps({"sheets": sheets}, ensure_ascii=False), encoding="utf-8")
    write_index(sheets, out)
    size = (out / "index.md").stat().st_size
    print(f"{len(sheets)} sheet(s), {sum(len(s['views']) for s in sheets)} views -> {out}/index.md "
          f"({size:,} bytes, about {size // 4:,} tokens)")
    for s in sheets:
        if s["flag"]:
            print(f"  {s['sheet']}: {s['flag']}", file=sys.stderr)


if __name__ == "__main__":
    main()
