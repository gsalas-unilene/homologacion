"""Own-catalog CodSut parser and a text parser that produces the same attribute schema.

A CodSut has 21 characters: marca(2) hebra(2) calibre(3) aguja(2) long_aguja(3) long_hebra(3) caja(2)
clase(1) campo_variable(3). Codes are decoded with ``items/codsut_estructura.json`` (converted from the
Unilene workbook by ``convertir_estructura.py``). Unknown or blank codes yield None for that attribute.
Both parsers return: marca, hebra, familia, variante (frozenset of tags), calibre, curvatura, punta,
long_aguja (mm), hebras, long_hebra (cm), caja, clase, doble (double needle).
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from homologador.atributos import norm, parse

ESTRUCTURA = Path(__file__).resolve().parents[2] / "items" / "codsut_estructura.json"

# hebra code -> (material family, tags). Families use the names of atributos.MATERIALS.
HEBRAS = {
    "AP": ("PGA", ()), "AA": ("PGA", ("antibacterial",)), "AI": ("PGA", ("incoloro",)),
    "AQ": ("ACERO", ()), "HM": ("ACERO", ("marcapaso",)), "CC": ("CATGUT CROMICO", ()), "CS": ("CATGUT SIMPLE", ()),
    "LI": ("LINO", ()),
    "NM": ("NYLON", ("azul", "monofilamento")), "NL": ("NYLON", ("natural", "monofilamento")),
    "NN": ("NYLON", ("negro", "monofilamento")), "NT": ("NYLON", ("negro", "trenzado")),
    "PD": ("PDO", ()), "PB": ("PDO", ("antibacterial",)), "DB": ("PDO", ("barbed",)), "DI": ("PDO", ("incoloro",)),
    "BY": ("PDO", ("violeta", "barbed")),
    "PW": ("POLIESTER", ("blanco",)), "PF": ("POLIESTER", ("teflon",)), "PL": ("POLIESTER", ("verde",)),
    "UZ": ("POLIETILENO", ("azul",)), "UW": ("POLIETILENO", ("blanco",)), "UN": ("POLIETILENO", ("blanco", "nucleo")),
    "UA": ("POLIETILENO", ("blanco", "azul")), "UV": ("POLIETILENO", ("blanco", "verde")),
    "UM": ("POLIETILENO", ("blanco", "violeta")), "UC": ("POLIETILENO", ("blanco", "negro")),
    "UB": ("POLIETILENO", ("negro",)), "UG": ("POLIETILENO", ("verde",)),
    "AG": ("PGLA", ()), "PA": ("PGLA", ("antibacterial",)), "PX": ("PGLA", ("antibacterial", "incoloro")),
    "PI": ("PGLA", ("incoloro",)), "PQ": ("PGLA", ("quick",)),
    "PG": ("PGC", ()), "PT": ("PGC", ("antibacterial",)), "PN": ("PGC", ("incoloro",)),
    "PH": ("PGC", ("incoloro", "antibacterial")), "BZ": ("PGC", ("violeta", "barbed")),
    "PP": ("POLIPROPILENO", ()), "BP": ("POLIPROPILENO", ("barbed",)),
    "FN": ("POLIPROPILENO", ("fluorescente", "naranja")), "FR": ("POLIPROPILENO", ("fluorescente", "rosado")),
    "FV": ("POLIPROPILENO", ("fluorescente", "verde")), "PO": ("POLIPROPILENO", ("incoloro",)),
    "BT": ("SEDA", ("blanco", "trenzado")), "ST": ("SEDA", ("negro", "trenzado")),
    "SA": ("SEDA", ("virgen", "azul")), "SN": ("SEDA", ("virgen", "negro")),
}
CURVATURES = r"(1/8|1/4|3/8|1/2|5/8)"
# Needle point keywords, first match wins (specific before generic).
PUNTAS = [
    (r"REVERS[EO] (?:CORTANTE|CUTTING)|CUTTING REVERS", "reverso cortante"),
    (r"ESPATULA|SPATULA", "espatulada"),
    (r"TAPERCUT", "tapercut"),
    (r"TAPERPOINT|TAPER POINT", "taper"),
    (r"MICROPUNTA", "micropunta"),
    (r"TROCAPOINT", "trocar"),
    (r"PUNTA ROMA|BLUNT", "roma"),
    (r"CORTANTE|CUTTING", "cortante"),
    (r"REDOND[AO]", "redonda"),
]
TAGS = [
    (r"ANTIBACTERIAL", "antibacterial"), (r"INCOLORO", "incoloro"), (r"BARBAD|PUAS", "barbed"),
    (r"VIOLETA", "violeta"), (r"NEGR[AO]", "negro"), (r"AZUL", "azul"), (r"BLANC[AO]", "blanco"),
    (r"VERDE", "verde"), (r"NATURAL", "natural"), (r"MONOFILAMENTO", "monofilamento"), (r"TRENZAD[AO]", "trenzado"),
    (r"FLUORESCENTE", "fluorescente"), (r"ROSAD[AO]", "rosado"), (r"NARANJA", "naranja"),
    (r"QUICK|RAPID[AO]", "quick"), (r"MARCAPASO", "marcapaso"), (r"TEFLON", "teflon"),
]
# Tag dimensions: color and construction are compared only when both sides state one.
DIMENSIONES = {"color": {"negro", "azul", "blanco", "verde", "violeta", "natural", "rosado", "naranja", "virgen"},
               "construccion": {"monofilamento", "trenzado"}}


@lru_cache(maxsize=1)
def _estructura() -> dict:
    return json.loads(ESTRUCTURA.read_text(encoding="utf-8"))


def _vacio() -> dict:
    return {"marca": None, "hebra": None, "familia": None, "variante": frozenset(), "calibre": None,
            "curvatura": None, "punta": None, "long_aguja": None, "hebras": None, "long_hebra": None,
            "caja": None, "clase": None, "doble": False}


def punta_de_texto(t: str) -> str | None:
    """Needle point from normalized text (dictionary descriptions and MINSA/Item names)."""
    for pattern, value in PUNTAS:
        if re.search(pattern, t):
            return value
    return None


def curvatura_de_descripcion(t: str) -> str | None:
    if "CARRETE" in t:
        return "carrete"
    for pattern, value in (("SIN AGUJA", "sin aguja"), ("MULTIEMPAQUE", "multiempaque")):
        if pattern in t:
            return value
    match = re.search(CURVATURES, t)
    if match:
        return match.group(1)
    for pattern, value in ((r"CURVA COMPUESTA", "curva compuesta"), (r"\bRECTA\b|STRAIGHT", "recta"),
                           (r"JOTA|\bEN J\b", "jota"), (r"FISH", "gancho")):
        if re.search(pattern, t):
            return value
    return None


def _largo_hebra(descripcion: str) -> float | None:
    match = re.fullmatch(r"(\d+(?:\.\d+)?) (cm|Metros|yd|pulgadas)", descripcion)
    if not match:
        return None
    factor = {"cm": 1, "Metros": 100, "yd": 91.44, "pulgadas": 2.54}[match.group(2)]
    return round(float(match.group(1)) * factor, 2)


def parse_codsut(codsut) -> dict:
    """Decode a CodSut positionally; anything blank, truncated or not in the dictionaries stays None."""
    a = _vacio()
    code = codsut.strip() if isinstance(codsut, str) else ""
    if len(code) < 17:
        return a
    d = _estructura()
    marca, hebra, calibre, aguja = code[0:2], code[2:4], code[4:7], code[7:9]
    long_aguja, long_hebra, caja, clase = code[9:12], code[12:15], code[15:17], code[17:18]
    a["marca"] = marca if marca in d["marca"] else None
    if hebra in HEBRAS and hebra in d["hebra"]:
        a["hebra"] = hebra
        a["familia"], tags = HEBRAS[hebra]
        a["variante"] = frozenset(tags)
    description = d["calibre"].get(calibre)
    a["calibre"] = None if description in (None, "Sin Calibre") else description
    if aguja in d["aguja"]:
        text = norm(d["aguja"][aguja])
        a["curvatura"] = curvatura_de_descripcion(text)
        a["punta"] = punta_de_texto(text) if a["curvatura"] not in ("sin aguja", "carrete", "multiempaque") else None
    description = d["long_aguja"].get(long_aguja, "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?) mm", description)
    a["long_aguja"] = float(match.group(1)) if match else None
    match = re.fullmatch(r"(\d+) hebras", description)
    a["hebras"] = int(match.group(1)) if match else None
    a["long_hebra"] = _largo_hebra(d["long_hebra"].get(long_hebra, ""))
    a["caja"] = caja if caja in d["caja"] and caja != "00" else None
    a["clase"] = clase if clase in d["clase"] else None
    a["doble"] = a["clase"] in ("B", "M")
    return a


def atributos_texto(texto: str) -> dict:
    """Same schema as ``parse_codsut`` from a MINSA name or an own ``Item`` name."""
    a = _vacio()
    old, t = parse(texto), norm(texto)
    a["familia"], a["calibre"] = old["mat"], old["gauge"]
    a["variante"] = frozenset(tag for pattern, tag in TAGS if re.search(pattern, t))
    if "MULTIEMPAQUE" in t:
        a["curvatura"] = "multiempaque"
    elif "CARRETE" in t:
        a["curvatura"] = "carrete"
    elif re.search(r"\bS/A|SIN AGUJA", t):
        a["curvatura"] = "sin aguja"
    else:
        a["curvatura"] = curvatura_de_descripcion(t.replace("AGUJA", ""))
        a["punta"] = punta_de_texto(t)
    a["long_aguja"] = float(old["mm"]) if old["mm"] else None
    a["long_hebra"] = float(old["cm"]) if old["cm"] else None
    match = re.search(r"(\d+) HEBRAS", t)
    a["hebras"] = int(match.group(1)) if match else None
    a["doble"] = old["needles"] == 2
    return a


def atributos_item(codsut, item: str) -> dict:
    """CodSut attributes, with the ``Item`` text filling whatever the code does not give."""
    a = parse_codsut(codsut)
    text = atributos_texto(item)
    for key in ("familia", "calibre", "curvatura", "punta", "long_aguja", "long_hebra", "hebras"):
        if a[key] is None:
            a[key] = text[key]
    if not a["variante"]:
        a["variante"] = text["variante"]
    if a["clase"] is None:
        a["doble"] = text["doble"]
    return a
