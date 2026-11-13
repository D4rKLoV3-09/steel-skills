"""SJII marks -> sections, unit weights and m2/m from the Consteel 2025 catalogue (generate-mto/references)."""
import re
from pathlib import Path

CAT = (Path(__file__).resolve().parents[2] / "generate-mto" / "references" / "consteel_catalogue.md").read_text(encoding="utf-8")
# mark -> drawing designation (Steel Fabricated Framing / Column schedules on the GA and truss sheets)
SCHED = {
    "B35D": "UB356x171x51", "B40C": "UB406x178x54", "B45E": "UB457x152x74.2", "B45J": "UB457x191x74.3",
    "B45N": "UB457x191x98.3", "B45Q": "UB457x279x113.1", "B53H": "UB533x210x109", "B53J": "UB533x210x122",
    "B53L": "UB533x210x138.4", "B53T": "UB533x312x270.8", "B61S": "UB610x305x149", "B61T": "UB610x305x179",
    "B61V": "UB610x324x154.8", "B76F": "UB762x267x196.8", "B83A": "UB838x292x175.9", "B83D": "UB838x292x226",
    "B101A": "UB1016x305x222", "B101F": "UB1016x305x393", "B101M": "UB1016x305x584", "B111D": "UB1118x406x499",
    "BU09": "UC465x421x589", "C30G": "UC356x368x177", "C35F": "UC356x368x177", "C35K": "UC356x406x175.6",
    "C35M": "UC356x406x235.1", "C35W": "UC356x406x393", "C35Z": "UC356x406x467", "C35CC": "UC356x406x592.3",
    "C35FF": "UC356x406x744.1", "C35JJ": "UC356x406x989.6", "C35KK": "UC356x406x1086",
    "R20A": "RHS200x100x5", "S20G": "SHS200x200x16", "S30H": "SHS300x300x16", "S50D": "SHS500x500x22",
    "D40H": "CHS406.4x14.2", "SC01": "SHS1200x1200x30",
}
_m2m = {}
for kg, d, b, a in re.findall(r"([\d.]+) \(([\d.]+)x([\d.]+)\) ([\d.]+)", CAT.split("### IPE")[0]):
    _m2m[(float(kg), float(d), float(b))] = float(a)
_groups = {}
for grp, body in re.findall(r"- \*\*(\d+)\*\*: ([^\n]+)", CAT.split("### UB / UC - Universal")[1].split("### IPE")[0]):
    _groups[int(grp)] = [tuple(map(float, x)) for x in re.findall(r"([\d.]+) \(([\d.]+)x([\d.]+)\)", body)]


def _hollow(kind, dims, t, form="hot finished"):
    sec = CAT.split(f"### {kind} - {form}")[1].split("###")[0]
    m = re.search(rf"^- {re.escape(dims)}: ([^\n]+)", sec, re.M)
    if m:
        for tt, kg in re.findall(r"t([\d.]+)=([\d.]+)", m.group(1)):
            if float(tt) == t:
                return float(kg)
    return None


def lookup(mark):
    """-> dict(name, type, geometry dims, kgm, m2m, m2m_assumed, kg_assumed, src)."""
    des = SCHED[mark]
    m = re.match(r"(UB|UC)(\d+)x(\d+)x([\d.]+)", des)
    if m:
        h, b, kg = int(m.group(2)), int(m.group(3)), float(m.group(4))
        cands = [c for g, cs in _groups.items() for c in cs if 0.92 * h < c[1] < 1.7 * h and abs(c[2] - b) / b < 0.13]
        best = min(cands, key=lambda c: abs(c[0] - kg), default=None)
        if best and abs(best[0] - kg) <= max(1.0, 0.01 * kg):
            k, D, B = best
            a = _m2m.get(best)
            A = k / 7.85e-3                                    # mm2
            tf = A / (2 * B + 0.6 * (D - 2 * A / (2 * B + 0.6 * D)))  # tw = 0.6 tf (display only)
            tf = A / (2 * B + 0.6 * (D - 2 * tf))
            return {"name": des, "type": "I", "h": D, "b": B, "tw": round(0.6 * tf, 1), "tf": round(tf, 1), "kgm": k,
                    "m2m": a if a else round((2 * D + 4 * B - 2 * 0.6 * tf) / 1000, 2), "m2m_assumed": a is None, "kg_assumed": False,
                    "src": f"Consteel 2025 UB/UC {k:g} ({D:g}x{B:g})" + (f"; m2/m {a:g} Consteel" if a else "; m2/m computed - ASSUMED")
                    + "; tw/tf from kg/m (display only)"}
        # not in Consteel: drawing designation, outline per nominal size
        D, B = {"UB1016x305x584": (1056, 314), "UB1118x406x499": (1118, 405)}.get(des, (h, b))
        A = kg / 7.85e-3
        tf = A / (2 * B + 0.6 * D)
        return {"name": des, "type": "I", "h": D, "b": B, "tw": round(0.6 * tf, 1), "tf": round(tf, 1), "kgm": kg,
                "m2m": round((2 * D + 4 * B) / 1000, 2), "m2m_assumed": True, "kg_assumed": True,
                "src": f"{des} NOT IN CONSTEEL 2025 - drawing designation {kg:g} kg/m, D x B {D}x{B} ASSUMED; m2/m computed - ASSUMED"}
    m = re.match(r"(SHS|RHS)(\d+)x(\d+)x([\d.]+)", des) or re.match(r"(CHS)([\d.]+)x([\d.]+)", des)
    if m.group(1) == "CHS":
        od, t = m.group(2), float(m.group(3))
        kg = _hollow("CHS", od, t)
        return {"name": des, "type": "SHS", "b": round(float(od) * 0.886, 1), "t": t, "kgm": kg, "m2m": round(3.1416 * float(od) / 1000, 3),
                "m2m_assumed": True, "kg_assumed": False, "src": f"Consteel 2025 CHS hot finished {od} t{t:g} {kg:g} (hot-finished assumed); "
                "m2/m computed - ASSUMED; shown as an equal-area square in the model"}
    kind, d, b, t = m.group(1), int(m.group(2)), int(m.group(3)), float(m.group(4))
    kg, form = _hollow(kind, f"{d}x{b}", t), "hot finished"
    if kg is None:                                   # size only rolled cold-formed (e.g. RHS200x100x5)
        kg, form = _hollow(kind, f"{d}x{b}", t, "cold formed"), "cold formed"
    ass = kg is None
    if ass:
        kg = round(((d * b) - (d - 2 * t) * (b - 2 * t)) * 7.85e-3, 1)
    return {"name": des, "type": "SHS" if d == b else "RHS", "b": b, "h": d, "t": t, "kgm": kg, "m2m": round(2 * (d + b) / 1000, 3),
            "m2m_assumed": True, "kg_assumed": ass,
            "src": (f"Consteel 2025 {kind} {form} {d}x{b} t{t:g} {kg:g} ({form} assumed)" if not ass else
                    f"{des} NOT IN CONSTEEL 2025 - {kg:g} kg/m computed at 7.85 - ASSUMED") + "; m2/m computed - ASSUMED"}


if __name__ == "__main__":
    for k in SCHED:
        r = lookup(k)
        print(f"{k:6} {r['name']:20} {r['kgm']:8} {r.get('h', '')!s:7} {r['b']:7} m2m {r['m2m']}{' *' if r['m2m_assumed'] else ''}"
              f"{'  KG ASSUMED' if r['kg_assumed'] else ''}")
