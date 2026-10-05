"""Tier a MINSA row from its top vector candidates (candidates for human review, not clinical equivalence)."""

from homologador.atributos import core_exact, parse, parse_item, score
from homologador.generico import MAX_DISTANCE, elegir

COLUMNS = ["CodigoMed", "NombreMed", "Coditem", "Item", "Agrupador", "tier", "distance", "score", "alt_2", "alt_3"]


def _result(tier, best, distance, points, alternatives):
    alts = [c["Coditem"] for c in alternatives[:2]] + ["", ""]
    return {
        "Coditem": best["Coditem"] if best else "",
        "Item": best["Item"] if best else "",
        "Agrupador": best["Agrupador"] if best else "",
        "tier": tier,
        "distance": distance,
        "score": points,
        "alt_2": alts[0] if best else "",
        "alt_3": alts[1] if best else "",
    }


def clasificar(nombre: str, candidatos: list[dict]) -> dict:
    """``candidatos``: vector neighbours (Coditem, Item, Agrupador, _distance), nearest first."""
    wanted = parse(nombre)
    if nombre.startswith("SUTURA") and wanted["mat"]:
        return _sutura(wanted, candidatos)
    return _generico(nombre, candidatos)


def _sutura(wanted: dict, candidatos: list[dict]) -> dict:
    ranked = sorted(
        ((score(wanted, parse_item(c["Item"])), parse_item(c["Item"]), c) for c in candidatos),
        key=lambda t: (-t[0], t[2]["_distance"]),
    )
    points, attrs, best = ranked[0]
    alternatives = [c for _, _, c in ranked[1:]]
    # An attribute-exact match is accepted at any distance: the attributes, not the embedding, vouch for it.
    if core_exact(wanted, attrs):
        return _result("exacto", best, best["_distance"], points, alternatives)
    if attrs["mat"] == wanted["mat"] and best["_distance"] <= MAX_DISTANCE:
        return _result("revisar", best, best["_distance"], points, alternatives)
    return _result("sin_equivalente", None, best["_distance"], points, [])


def _generico(nombre: str, candidatos: list[dict]) -> dict:
    nearest = min(c["_distance"] for c in candidatos)
    ranked = elegir(nombre, candidatos)
    if ranked and ranked[0][0] == 0:
        penalty, best = ranked[0]
        return _result("revisar", best, best["_distance"], -penalty, [c for _, c in ranked[1:]])
    return _result("sin_equivalente", None, nearest, 0, [])
