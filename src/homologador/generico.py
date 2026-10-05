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

UNITS = {"MM": "MM", "CM": "CM", "ML": "ML", "CC": "ML", "MG": "MG", "MCG": "MCG", "KG": "KG", "GR": "G",
         "G": "G", "UI": "UI", "FR": "FR", "F": "FR", "L": "L", "M": "M", "%": "%", "AGUJEROS": "AGUJEROS"}
# "4.0/3.5 mm" and "3 g/100 g" give several numbers per unit; G is both grams and gauge (22 G), a known blur.
TOKEN = re.compile(
    r"(?<![\d.,])(\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?)*) ?(AGUJEROS|MCG|MM|CM|ML|MG|KG|UI|FR|GR|CC|G|F|L|M|%)(?![A-Z])"
)


def _number(value: str) -> str:
    return f"{float(value.replace(',', '.')):g}"


def medidas(texto: str) -> set[tuple[str, str]]:
    """Set of (number, unit) tokens, e.g. {('10', 'MM'), ('2.5', 'ML')}."""
    result = set()
    for numbers, unit in TOKEN.findall(norm(texto)):
        result.update((_number(number), UNITS[unit]) for number in numbers.split("/"))
    return result


def penalidad(a: set, b: set) -> int:
    return len(a ^ b)


def elegir(nombre: str, candidatos: list[dict], max_distance: float = MAX_DISTANCE) -> list[tuple[int, dict]]:
    """Candidates within ``max_distance`` as (penalty, candidate), best first: fewest number mismatches, then distance."""
    wanted = medidas(nombre)
    ranked = [(penalidad(wanted, medidas(c["Item"])), c) for c in candidatos if c["_distance"] <= max_distance]
    return sorted(ranked, key=lambda pair: (pair[0], pair[1]["_distance"]))
