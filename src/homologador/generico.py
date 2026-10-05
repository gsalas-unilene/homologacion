"""Generic (non-suture) strategy: compare number+unit tokens over vector candidates."""

import re

from homologador.atributos import norm

# L2 distance threshold, measured on the stored vectors (unit-normalized FastEmbed):
#   - best attribute-exact suture candidate, 233 sampled MINSA suture rows: p50 0.24, p95 0.32, max 0.42;
#   - nearest own item for 600 sampled non-suture MINSA rows: related products (catheters, fistula
#     needles, acyclovir ointment) start at 0.275; the first clearly unrelated neighbours (plates and
#     screws matched to sutures, hemostatic sponge) show up from 0.36 on.
# 0.35 keeps the related band and rejects the unrelated one; it is a review aid, not a clinical limit.
MAX_DISTANCE = 0.35
# Non-suture rows search only the 836 non-suture own items (no suture crowding). Re-measured on 400
# random non-suture MINSA rows: nearest-item distance p10 0.50, median 0.68. Plausible matches with
# agreeing numbers sit at 0.28-0.45 (aspiration tubes 0.32-0.36, central catheters, gloves of the same
# size 0.41-0.45) while junk with agreeing numbers starts at 0.47 (needle "N 21" -> blade "N 21",
# hand piece -> gloves). A name with no numbers agrees vacuously, so it keeps the strict 0.35.
MAX_DISTANCE_RELAJADO = 0.45

UNITS = {"MM": "MM", "CM": "CM", "ML": "ML", "CC": "ML", "MG": "MG", "MCG": "MCG", "KG": "KG", "GR": "G",
         "G": "G", "UI": "UI", "FR": "FR", "F": "FR", "L": "L", "M": "M", "%": "%", "AGUJEROS": "AGUJEROS"}
# "4.0/3.5 mm" and "3 g/100 g" give several numbers per unit; G is both grams and gauge (22 G), a known blur.
TOKEN = re.compile(
    r"(?<![\d.,])(\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?)*) ?(AGUJEROS|MCG|MM|CM|ML|MG|KG|UI|FR|GR|CC|G|F|L|M|%)(?![A-Z])"
)


SIZE = re.compile(r"\bN[°O]? ?(\d+(?:[.,]\d+)?)\b(?! ?(?:G|FR|F|MM|CM|ML)\b)")  # "N-degree 12", "NO 12": blade, probe sizes; "N-degree 23 G" is a gauge
TALLA = re.compile(r'(?:TALLA|ESTERIL) "?(XXL|XL|XS|S|M|L)"?(?![A-Z0-9])')  # "TALLA S", "NO ESTERIL S CP" (gloves, gowns)
INCH = re.compile(r"""(?<![\d/])(\d+ \d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?) ?(?:IN\b|"|'')""")  # 5/16 in, 1 1/2", 3 1/2''; never converted to mm


def _number(value: str) -> str:
    return f"{float(value.replace(',', '.')):g}"


def medidas(texto: str) -> set[tuple[str, str]]:
    """Set of (number, unit) tokens, e.g. {('10', 'MM'), ('2.5', 'ML')}."""
    t = norm(texto)
    result = {(_number(number), "N") for number in SIZE.findall(t)}
    result.update((size, "TALLA") for size in TALLA.findall(t))
    result.update((inch.replace(" ", "-").replace(",", "."), "IN") for inch in INCH.findall(t))
    for numbers, unit in TOKEN.findall(t):
        result.update((_number(number), UNITS[unit]) for number in numbers.split("/"))
    return result


def penalidad(a: set, b: set) -> int:
    return len(a ^ b)


def elegir(nombre: str, candidatos: list[dict]) -> list[tuple[int, dict]]:
    """Candidates as (penalty, candidate), best first: fewest number mismatches, then distance.

    Distance limit: relaxed when the name carries numbers, strict otherwise (see MAX_DISTANCE_RELAJADO).
    """
    wanted = medidas(nombre)
    limit = MAX_DISTANCE_RELAJADO if wanted else MAX_DISTANCE
    ranked = [(penalidad(wanted, medidas(c["Item"])), c) for c in candidatos if c["_distance"] <= limit]
    return sorted(ranked, key=lambda pair: (pair[0], pair[1]["_distance"]))
