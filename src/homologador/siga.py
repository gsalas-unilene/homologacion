"""Choose the best SIGA catalog option for a MINSA description.

SIGA lists search results by code, not by relevance, and its wording differs from MINSA's (NAILON for
NYLON, C/DOBLE AGUJA for C/2A, no Nº...). The options found by every search (first pass plus the
variants of the second pass) are therefore scored by attributes: suture names are compared attribute
by attribute (same parser as the homologation), other names by number+unit tokens, head word,
qualifiers and word overlap. Estados: exacto (normalized text equal), mejor_coincidencia (all core
attributes agree), aproximado (a core attribute differs or is missing in SIGA), ambiguo (two or more
options tied at the top), sin_resultado. Candidates for human review, not clinical equivalence.
"""

import re

from homologador.atributos import norm, parse
from homologador.clasificar import es_sutura
from homologador.codsut import DIMENSIONES, atributos_texto
from homologador.generico import STOPWORDS, _cualificadores, _palabras, medidas, penalidad

EQ, NO_PEDIDO, DESCONOCIDO, DIFF = "eq", "no_pedido", "desconocido", "diff"
SIN_AGUJA = ("sin aguja", "multiempaque", "carrete")
ESPECIAL = DIMENSIONES["color"] | DIMENSIONES["construccion"]
MAX_OPCIONES = 5


def candidatos(raw1: list, raw2: list) -> list[dict]:
    """Union of the rows of the first pass and of every variant search, deduped by code (first seen order)."""
    union: dict[str, dict] = {}
    for fuente, rows in [("pasada1", raw1)] + [(v["v"], v["rows"]) for v in raw2]:
        for codigo, descripcion in rows:
            entry = union.setdefault(codigo, {"codigo": codigo, "descripcion": descripcion, "fuentes": []})
            if fuente not in entry["fuentes"]:
                entry["fuentes"].append(fuente)
    return list(union.values())


def clave(texto: str) -> str:
    """Normalized text for the exact test: no accents or case, Nº/N°/NO alike, inch marks as IN, no
    parenthesized notes, no trailing UNIDAD."""
    t = re.sub(r"\([^)]*\)", " ", texto).replace("*", " ")
    t = norm(t).replace('"', " IN ").replace("''", " IN ")
    t = re.sub(r"\bN°\s*", "NO ", t)
    t = re.sub(r"[^A-Z0-9/. ]", " ", t)
    t = re.sub(r"\s+(UNIDAD|UND|UNI|INYECTABLE)\s*$", "", " ".join(t.split()))
    return " ".join(t.split())


def _ordinal(calibre):
    """Position on the USP scale: ... 3/0=-3, 2/0=-2, 1/0=0=-1, 1=0, 2=1 ..."""
    if calibre is None:
        return None
    if re.fullmatch(r"\d+/0", calibre):
        return -int(calibre.split("/")[0])
    if calibre == "0":
        return -1
    return int(calibre) - 1 if calibre.isdigit() else None


def _estado(pedido, hallado):
    if pedido is None:
        return NO_PEDIDO
    if hallado is None:
        return DESCONOCIDO
    return EQ if pedido == hallado else DIFF


def _num(valor) -> str:
    return f"{valor:g}"


def _fmt(valor) -> str:
    return "?" if valor is None else str(valor)


def _etiqueta(tags) -> str:
    return ",".join(sorted(tags)) or "-"


def _comparar_sutura(m: dict, s: dict) -> dict:
    """Penalty (0 = identical), core agreement flag and MINSA!=SIGA differences for one SIGA option."""
    penalty, diffs, core_ok = 0.0, [], True

    def anotar(clave_, pedido, hallado, estado, peso):
        nonlocal penalty, core_ok
        if estado in (DIFF, DESCONOCIDO):
            penalty += peso if estado == DIFF else peso / 2
            core_ok = False
            diffs.append(f"{clave_}:{_fmt(pedido)}!={_fmt(hallado)}")

    anotar("familia", m["familia"], s["familia"], _estado(m["familia"], s["familia"]), 40)
    pedido, hallado = _ordinal(m["calibre"]), _ordinal(s["calibre"])
    estado = _estado(m["calibre"], s["calibre"])
    peso = 25 + 3 * min(abs(pedido - hallado), 5) if estado == DIFF and None not in (pedido, hallado) else 30
    anotar("calibre", m["calibre"], s["calibre"], estado, peso)
    # A multipack, spool or needle-less thread is another kind of product than a needled one.
    clase_distinta = (m["curvatura"] in SIN_AGUJA or s["curvatura"] in SIN_AGUJA) and m["curvatura"] != s["curvatura"]
    anotar("curvatura", m["curvatura"], s["curvatura"], _estado(m["curvatura"], s["curvatura"]), 35 if clase_distinta else 15)
    sin_punta = m["curvatura"] in SIN_AGUJA or s["curvatura"] in SIN_AGUJA
    if not sin_punta:
        anotar("punta", m["punta"], s["punta"], _estado(m["punta"], s["punta"]), 10)
        anotar("agujas", 2 if m["doble"] else 1, 2 if s["doble"] else 1, EQ if m["doble"] == s["doble"] else DIFF, 25)
    # Attributes SIGA states but the MINSA name does not: not a mismatch, but the plainer option ranks first.
    penalty += 0.5 * sum(m[k] is None and s[k] is not None for k in ("curvatura", "punta"))
    mt, st = m["variante"], s["variante"]
    penalty += 0.5 * sum(not (mt & d) and bool(st & d) for d in DIMENSIONES.values())
    variante = DIFF if any(a and b and a != b for a, b in ((mt & d, st & d) for d in DIMENSIONES.values())) \
        or (mt - ESPECIAL) != (st - ESPECIAL) else EQ
    if variante == DIFF:
        penalty += 12
        core_ok = False  # another color, construction or special thread is another product
        diffs.append(f"variante:{_etiqueta(mt)}!={_etiqueta(st)}")
    for key, unidad, peso_largo in (("hebras", "", 4), ("long_aguja", "mm", 0.8), ("long_hebra", "cm", 0.2)):
        estado = _estado(m[key], s[key])
        if estado == DIFF:
            penalty += peso_largo * (4 if key == "hebras" else min(abs(m[key] - s[key]), 10 if key == "long_aguja" else 30))
            diffs.append(f"{key}:{_num(m[key])}!={_num(s[key])}{unidad}")
        elif estado == DESCONOCIDO:
            penalty += 2
            diffs.append(f"{key}:{_num(m[key])}!=?{unidad}")
    if m["familia"] is None or m["calibre"] is None:
        core_ok = False  # nothing to confirm the material or size against
    return {"penalty": penalty, "core_ok": core_ok, "diffs": diffs}


def _palabras_por_prefijo(texto: str) -> dict:
    """{4-letter prefix: full word} of the meaningful words, to list differences in readable form."""
    return {w[:4]: w for w in re.findall(r"[A-Z]{3,}", norm(texto)) if w not in STOPWORDS}


def _comparar_generico(nombre: str, descripcion: str) -> dict:
    pedido, hallado = medidas(nombre), medidas(descripcion)
    palabras_a, palabras_b = set(_palabras(norm(nombre))), set(_palabras(norm(descripcion)))
    union = palabras_a | palabras_b
    jaccard = len(palabras_a & palabras_b) / len(union) if union else 1.0
    cobertura = len(palabras_a & palabras_b) / len(palabras_a) if palabras_a else 1.0
    faltan, sobran = sorted(f"{n} {u}" for n, u in pedido - hallado), sorted(f"{n} {u}" for n, u in hallado - pedido)
    penalty = 12 * min(penalidad(pedido, hallado), 5) + (1 - jaccard) * 30
    compat = _compatibles_cualificadores(nombre, descripcion)
    if not compat:
        penalty += 30
    diffs = []
    if faltan or sobran:
        diffs.append(f"medidas:{', '.join(faltan) or '-'}!={', '.join(sobran) or '-'}")
    wa, wb = _palabras_por_prefijo(nombre), _palabras_por_prefijo(descripcion)
    sin_cubrir = sorted(w for k, w in wa.items() if k not in wb)
    if sin_cubrir:
        diffs.append(f"palabras:{', '.join(sin_cubrir[:4])}!={', '.join(sorted(w for k, w in wb.items() if k not in wa)[:4]) or '-'}")
    qa, qb = _cualificadores(norm(nombre)), _cualificadores(norm(descripcion))
    diffs += [f"{k}:{qa[k]}!={qb[k]}" for k in sorted(qa.keys() & qb.keys()) if qa[k] != qb[k]]
    # Every MINSA word but at most a quarter must appear in SIGA ("GUANTE DE LATEX ... EXAMEN" is not a latex-neoprene glove).
    core_ok = compat and penalidad(pedido, hallado) == 0 and jaccard >= 0.4 and cobertura >= 0.75
    if not core_ok:
        penalty += 10
    return {"penalty": penalty, "core_ok": core_ok, "diffs": diffs}


def _compatibles_cualificadores(nombre: str, descripcion: str) -> bool:
    from homologador.generico import compatibles

    return compatibles(nombre, descripcion)


def _puntaje(comparacion: dict) -> int:
    """100 only for a normalized-equal description; otherwise at most 99, lower with each difference."""
    if comparacion["penalty"] < 0:
        return 100
    return max(0, min(99, round(100 - comparacion["penalty"])))


def elegir(nombre: str, opciones: list[dict]) -> dict:
    """Rank ``opciones`` (from ``candidatos``) for the MINSA ``nombre``; see the module docstring."""
    if not opciones:
        return {"estado": "sin_resultado", "puntaje": 0, "opciones": [], "diferencias": "", "total": 0}
    suturas = es_sutura(nombre)
    pedido = atributos_texto(nombre) if suturas else None
    gauge = parse(nombre)["gauge"] if suturas else None
    objetivo = clave(nombre)
    evaluadas = []
    for opcion in opciones:
        if clave(opcion["descripcion"]) == objetivo:
            cmp_ = {"penalty": -1.0, "core_ok": True, "diffs": []}
            notacion = 0
        else:
            if suturas:
                cmp_ = _comparar_sutura(pedido, atributos_texto(opcion["descripcion"]))
                notacion = 0 if parse(opcion["descripcion"])["gauge"] == gauge else 1
            else:
                cmp_ = _comparar_generico(nombre, opcion["descripcion"])
                notacion = 0
        evaluadas.append(((round(cmp_["penalty"], 3), notacion), opcion, cmp_))
    evaluadas.sort(key=lambda t: (t[0], t[1]["codigo"]))
    clave_top, _, mejor = evaluadas[0]
    empatadas = [t for t in evaluadas if t[0] == clave_top]
    if mejor["penalty"] < 0:
        estado = "ambiguo" if len(empatadas) > 1 else "exacto"
    elif mejor["core_ok"]:
        estado = "ambiguo" if len(empatadas) > 1 else "mejor_coincidencia"
    else:
        estado = "aproximado"
    puntaje = _puntaje(mejor)
    return {
        "estado": estado,
        "puntaje": puntaje,
        "opciones": [{"codigo": o["codigo"], "descripcion": o["descripcion"],
                      "puntaje": _puntaje(c)} for _, o, c in evaluadas],
        "diferencias": "; ".join(mejor["diffs"]),
        "total": len(opciones),
    }
