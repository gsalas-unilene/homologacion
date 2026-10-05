"""Tier a MINSA row from its top vector candidates (candidates for human review, not clinical equivalence)."""

from homologador.atributos import parse
from homologador.generico import elegir
from homologador.suturas import emparejar

COLUMNS = ["CodigoMed", "NombreMed", "Coditem", "Item", "Agrupador", "tier", "distance", "score", "alt_2", "alt_3",
           "marca", "CodSut", "diferencias"]


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


def es_sutura(nombre: str) -> bool:
    """Suture path: named SUTURA with a recognized material. Everything else is searched among non-suture items."""
    return nombre.startswith("SUTURA") and parse(nombre)["mat"] is not None


def clasificar(nombre: str, candidatos: list[dict], indice: dict | None = None) -> dict:
    """Suture rows are matched on the SD/CQ structured ``indice``; other rows on ``candidatos``
    (vector neighbours with Coditem, Item, Agrupador, _distance, nearest first)."""
    if es_sutura(nombre):
        return emparejar(nombre, indice)
    return _generico(nombre, candidatos)


def _generico(nombre: str, candidatos: list[dict]) -> dict:
    nearest = min(c["_distance"] for c in candidatos)
    ranked = elegir(nombre, candidatos)
    if ranked and ranked[0][0] == 0:
        penalty, best = ranked[0]
        return _result("revisar", best, best["_distance"], -penalty, [c for _, c in ranked[1:]])
    return _result("sin_equivalente", None, nearest, 0, [])
