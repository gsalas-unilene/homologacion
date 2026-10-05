"""Structured suture matching against own SUTUMED (SD) and CIRUGIA PERUANA PLUS (CQ) items.

Candidates come from the CodSut of the own items, indexed by (material family, calibre); the MINSA name
is parsed with the same attribute schema (``codsut.atributos_texto``). A missing attribute in the MINSA
name is unknown, not a mismatch. Tiers are candidates for human review, not clinical equivalence.
"""

import csv
from pathlib import Path

from homologador.codsut import DIMENSIONES, atributos_item, atributos_texto

MARCAS = ("SD", "CQ")
SIN_AGUJA = ("sin aguja", "multiempaque", "carrete")
EQ, UNKNOWN, DIFF = 0, 1, 2


def indexar(rows) -> dict:
    """{(familia, calibre): [entries]} for the SD/CQ items of the suture group that have a known family."""
    index = {}
    for row in rows:
        if row["Agrupador"] != "01. SUTURAS" or row["CodSut"].strip()[:2] not in MARCAS:
            continue
        attrs = atributos_item(row["CodSut"], row["Item"])
        if attrs["familia"] is None:
            continue
        marca = row["CodSut"].strip()[:2]
        entry = {"Coditem": row["Coditem"], "CodSut": row["CodSut"].strip(), "Item": row["Item"],
                 "Agrupador": row["Agrupador"], "marca": marca, "attrs": attrs}
        index.setdefault((attrs["familia"], attrs["calibre"]), []).append(entry)
    return index


def cargar_indice(items_csv: Path) -> dict:
    with Path(items_csv).open(encoding="utf-8-sig", newline="") as stream:
        return indexar(csv.DictReader(stream))


def _estado(wanted, found) -> int:
    if wanted is None or found is None:
        return UNKNOWN
    return EQ if wanted == found else DIFF


def _num(value) -> str:
    return f"{value:g}"


def _comparar(m: dict, i: dict) -> dict:
    """Per-attribute states and the human-readable differences between a MINSA name and an item."""
    core = {"curvatura": _estado(m["curvatura"], i["curvatura"])}
    sin_punta = m["curvatura"] in SIN_AGUJA or i["curvatura"] in SIN_AGUJA
    core["punta"] = EQ if sin_punta and core["curvatura"] == EQ else _estado(m["punta"], i["punta"])
    diffs = []
    for key in ("curvatura", "punta"):
        if core[key] != EQ:
            diffs.append(f"{key}:{m[key] or '?'}!={i[key] or '?'}")

    def vacio(value):
        return value or "-"

    mt, it = m["variante"], i["variante"]
    estados = []
    for dimension in DIMENSIONES.values():
        a, b = mt & dimension, it & dimension
        estados.append(UNKNOWN if not a and b else DIFF if a and b and a != b else EQ)
    special = DIMENSIONES["color"] | DIMENSIONES["construccion"]
    estados.append(EQ if mt - special == it - special else DIFF)
    variant = DIFF if DIFF in estados else UNKNOWN if UNKNOWN in estados else EQ
    if variant != EQ:
        diffs.append(f"variante:{vacio(','.join(sorted(mt)))}!={vacio(','.join(sorted(it)))}")
    secondary = {"variante": variant}
    if not sin_punta:
        secondary["agujas"] = EQ if m["doble"] == i["doble"] else DIFF
        if secondary["agujas"] == DIFF:
            diffs.append(f"agujas:{2 if m['doble'] else 1}!={2 if i['doble'] else 1}")
    for key, label, unit in (("hebras", "hebras", ""), ("long_aguja", "long_aguja", "mm"), ("long_hebra", "long_hebra", "cm")):
        if m[key] is None and i[key] is None:
            secondary[key] = EQ
        elif m[key] is None:
            secondary[key] = UNKNOWN
        elif m[key] == i[key]:
            secondary[key] = EQ
        else:
            secondary[key] = DIFF
            diffs.append(f"{label}:{_num(m[key])}!={'?' if i[key] is None else _num(i[key])}{unit}")
    return {"core": core, "secondary": secondary, "diffs": diffs}


def _distancia(a, b) -> float:
    return 0 if a is None or b is None else abs(a - b)


def _clave(m: dict, entry: dict, cmp: dict):
    i = entry["attrs"]
    return (
        cmp["core"]["curvatura"], cmp["core"]["punta"], cmp["secondary"]["variante"], cmp["secondary"].get("agujas", 0),
        cmp["secondary"]["hebras"] == DIFF,
        _distancia(m["long_aguja"], i["long_aguja"]) if m["long_aguja"] is not None and i["long_aguja"] is None else 0,
        _distancia(m["long_aguja"], i["long_aguja"]), _distancia(m["long_hebra"], i["long_hebra"]),
        MARCAS.index(entry["marca"]), entry["Coditem"],
    )


def _resultado(tier, entry, cmp, points, alternatives):
    alts = [e["Coditem"] for e in alternatives[:2]] + ["", ""]
    return {
        "Coditem": entry["Coditem"] if entry else "", "Item": entry["Item"] if entry else "",
        "Agrupador": entry["Agrupador"] if entry else "", "tier": tier, "distance": "", "score": points,
        "alt_2": alts[0] if entry else "", "alt_3": alts[1] if entry else "",
        "marca": entry["marca"] if entry else "", "CodSut": entry["CodSut"] if entry else "",
        "diferencias": "; ".join(cmp["diffs"]) if entry else "",
    }


def emparejar(nombre: str, indice: dict) -> dict:
    m = atributos_texto(nombre)
    if m["calibre"] is None:
        pool = [e for (familia, _), entries in indice.items() if familia == m["familia"] for e in entries]
    else:
        pool = indice.get((m["familia"], m["calibre"]), [])
    if not pool:
        return _resultado("sin_equivalente", None, None, 0, [])
    ranked = sorted(((_clave(m, e, c), e, c) for e in pool for c in [_comparar(m, e["attrs"])]), key=lambda t: t[0])
    _, best, cmp = ranked[0]
    core_ok = cmp["core"]["curvatura"] == EQ and cmp["core"]["punta"] == EQ and m["calibre"] is not None
    if not core_ok:
        tier = "revisar"
    elif all(state == EQ for state in cmp["secondary"].values()):
        tier = "exacto"
    else:
        tier = "probable"
    points = sum(state == EQ for state in cmp["core"].values()) + sum(state == EQ for state in cmp["secondary"].values())
    return _resultado(tier, best, cmp, points, [e for _, e, _ in ranked[1:]])
