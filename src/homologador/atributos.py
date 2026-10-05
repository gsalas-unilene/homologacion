"""Suture attribute parser and re-ranking score.

Vector search ranks sutures that differ only in gauge or needle poorly, so the
top candidates are re-ranked by comparing attributes parsed from the MINSA name
and the internal ``Item`` name. These are candidate scores for human review, not
clinical equivalence.
"""

import re
import unicodedata

# Order matters: the first substring found wins (specific before generic).
MATERIALS = [
    ("POLIGLICOLICO", "PGA"),
    ("POLIGLACTIN", "PGLA"),
    ("VICRYL", "PGLA"),
    ("DEXON", "PGLA"),
    ("POLIGLECAPRONE", "PGC"),
    ("POLIGLICONATO", "POLIGLICONATO"),
    ("POLIDIOXANONA", "PDO"),
    ("POLIPROPILEN", "POLIPROPILENO"),
    ("PROLENE", "POLIPROPILENO"),
    ("POLIESTER", "POLIESTER"),
    ("POLIETILENO", "POLIETILENO"),
    ("NYLON", "NYLON"),
    ("NAILON", "NYLON"),
    ("SEDA", "SEDA"),
    ("CROMICO", "CATGUT CROMICO"),
    ("CATGUT", "CATGUT SIMPLE"),
    ("ACERO", "ACERO"),
    ("ALAMBRE", "ACERO"),
    ("LINO", "LINO"),
    ("ADHESIVA", "ADHESIVA"),
]
CURVATURE = r"(?<!\d)(1/2|3/8|5/8|1/4)(?!\d)"
NO_NEEDLE = r"\bS/A|SIN AGUJA|MULTIEMPAQUE|CARRETE"
DOUBLE_NEEDLE = r"\bC/(?:2|DOBLE|CUATRO|4) ?A|\b2 ?C/A"
WEIGHTS = {"mat": 4, "gauge": 3, "curv": 1, "type": 1, "mm": 1, "cm": 1, "needles": 1}


def norm(text: str) -> str:
    """Upper-case, strip accents, collapse whitespace; U+FFFD (broken accent or degree sign) becomes a degree sign."""
    text = unicodedata.normalize("NFD", text.upper().replace("\ufffd", "\u00b0").replace("\u00ba", "\u00b0").replace("\u00bd", "1/2"))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", text).strip()


def _gauge(text: str, suture: bool) -> str | None:
    match = re.search(r"\b(\d{1,2}/0)\b", text) or re.search(r"\bN(?:O|°)?\s?(\d)\b", text)
    if match:
        return match.group(1)
    if not suture:
        return None
    # Plain integer gauge ("... TRENZADA 4 C/A", "... 1 1/2 CC"): the first lone digit that is not
    # part of a fraction or decimal and not a measure or strand count. Only for suture text.
    match = re.search(r"(?<![\d/.,])(\d)(?![\d/.,])(?! ?(?:MM|CM|HEBRAS|YD|YARDAS|METROS|MR\b))", text)
    return match.group(1) if match else None


def _type(text: str) -> str | None:
    for pattern, value in (
        (r"CORTANTE|(?<![A-Z])C[CT]\b", "CORTANTE"),
        (r"REDOND[AO]|(?<![A-Z])CR\b", "REDONDA"),
        (r"ESPATULA", "ESPATULADA"),
        (r"CILINDRICA", "CILINDRICA"),
        (r"CONICA", "CONICA"),
        (r"\bRECTA\b", "RECTA"),
    ):
        if re.search(pattern, text):
            return value
    return None


def parse(text: str) -> dict:
    """Parse suture attributes; missing ones are None. ``needles`` is 0, 1 or 2."""
    t = norm(text)
    mat = next((value for key, value in MATERIALS if key in t), None)
    attrs = {"mat": mat, "gauge": _gauge(t, mat is not None or "SUTURA" in t)}
    match = re.search(CURVATURE, t)
    attrs["curv"] = match.group(1) if match else "1/2" if "MEDIO CIRCULO" in t else None
    attrs["type"] = _type(t)
    match = re.search(r"(\d+(?:[.,]\d+)?) ?M{1,2}(?= ?X|\b)", t)
    attrs["mm"] = match.group(1).replace(",", ".") if match else None
    lengths = re.findall(r"(\d+(?:[.,]\d+)?) ?CM", t)
    attrs["cm"] = lengths[-1].replace(",", ".") if lengths else None
    attrs["needles"] = 0 if re.search(NO_NEEDLE, t) else 2 if re.search(DOUBLE_NEEDLE, t) else 1
    return attrs


def parse_item(text: str) -> dict:
    """Parse an internal ``Item`` name: same grammar plus a trailing two-letter supplier code (SD, VE, CP...)."""
    t = norm(text)
    t = re.sub(r" (?!CM$|MM$)[A-Z]{2}$", "", t)
    return parse(t)


def score(x: dict, y: dict) -> int:
    """Weighted agreement: +weight when equal, -weight when different, 0 when either side is unknown."""
    total = 0
    for key, weight in WEIGHTS.items():
        if x[key] is None or y[key] is None:
            continue
        total += weight if x[key] == y[key] else -weight
    return total


def core_exact(x: dict, y: dict) -> bool:
    """Material, gauge, curvature and needle type all known and equal; needle-less sutures compare length instead."""
    if x["needles"] == 0 or y["needles"] == 0:
        keys = ("mat", "gauge", "cm", "needles")
    else:
        keys = ("mat", "gauge", "curv", "type")
    return all(x[key] is not None and x[key] == y[key] for key in keys)
