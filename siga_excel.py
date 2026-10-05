"""Final Excel: homologated MINSA rows plus the best SIGA code and its alternatives.

Run from the repository root with ``uv run --with openpyxl python siga_excel.py``. openpyxl is needed
only to write the workbook (imported lazily; it is not a project dependency); the matching logic lives
in ``homologador.siga`` and works without it. Inputs, all in ``salida/``: ``homologacion.csv``,
``queries.json`` (row order -> cleaned query), ``siga_raw.json`` (first pass) and ``siga_raw2.json``
(search variants). Output: ``salida/homologacion_siga_final.xlsx``.
"""

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from homologador.siga import MAX_OPCIONES, candidatos, clave, elegir

SALIDA = Path(__file__).resolve().parent / "salida"
XLSX = SALIDA / "homologacion_siga_final.xlsx"
HOJA = "homologacion_siga"
COLUMNAS_SIGA = (["SIGA_estado", "SIGA_puntaje", "SIGA_codigo_1", "SIGA_descripcion_1", "SIGA_diferencias"]
                 + [f"SIGA_codigo_{n}" for n in range(2, MAX_OPCIONES + 1)] + ["SIGA_alternativas", "SIGA_total_opciones"])
ESTADOS = ("exacto", "mejor_coincidencia", "aproximado", "ambiguo", "sin_resultado")


def cargar_entradas(directorio: Path = SALIDA):
    """(rows, queries, raw1, raw2): the 1085 rows to homologate (not sin_equivalente, or any suture) and the scraped data."""
    with (directorio / "homologacion.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if r["tier"] != "sin_equivalente" or r["NombreMed"].startswith("SUTURA")]
    leer = lambda nombre: json.loads((directorio / nombre).read_text(encoding="utf-8"))
    return rows, leer("queries.json"), leer("siga_raw.json"), leer("siga_raw2.json")


def estado_pasada1(q: str, rows: list) -> str:
    """The estado of the first scraping pass (equal text, single result, several, none), for comparison."""
    if any(clave(descripcion) == clave(q) for _, descripcion in rows):
        return "exacto"
    return "sin_resultado" if not rows else "unico" if len(rows) == 1 else "multiple"


def _por_consulta(raw1: list, raw2: list):
    primera = {r["q"]: r["rows"] for r in raw1 if r.get("http") == 200 and not r.get("error")}
    variantes = defaultdict(list)
    for r in raw2:
        variantes[r["q"]].append(r)
    return primera, variantes


def construir_filas(rows: list, queries: list, raw1: list, raw2: list) -> list[dict]:
    """One dict per row: the original columns plus the SIGA ones (the options come from both passes)."""
    if len(rows) != len(queries):
        raise ValueError(f"{len(rows)} rows but {len(queries)} queries")
    primera, variantes = _por_consulta(raw1, raw2)
    filas = []
    for fila, consulta in zip(rows, queries):
        if fila["CodigoMed"] != consulta["cod"]:
            raise ValueError(f"row {fila['CodigoMed']} does not match query {consulta['cod']} (position {consulta.get('i')})")
        resultado = elegir(fila["NombreMed"], candidatos(primera.get(consulta["q"], []), variantes.get(consulta["q"], [])))
        opciones = resultado["opciones"][:MAX_OPCIONES]
        extra = {
            "SIGA_estado": resultado["estado"], "SIGA_puntaje": resultado["puntaje"],
            "SIGA_codigo_1": opciones[0]["codigo"] if opciones else "",
            "SIGA_descripcion_1": opciones[0]["descripcion"] if opciones else "",
            "SIGA_diferencias": resultado["diferencias"],
        }
        for n in range(2, MAX_OPCIONES + 1):
            extra[f"SIGA_codigo_{n}"] = opciones[n - 1]["codigo"] if len(opciones) >= n else ""
        extra["SIGA_alternativas"] = " | ".join(f"{o['codigo']}: {o['descripcion']}" for o in opciones[1:])
        extra["SIGA_total_opciones"] = resultado["total"]
        filas.append({**fila, **extra})
    return filas


def escribir_xlsx(filas: list[dict], ruta: Path = XLSX) -> None:
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

    libro = Workbook()
    hoja = libro.active
    hoja.title = HOJA
    columnas = list(filas[0])
    hoja.append(columnas)
    for fila in filas:
        hoja.append([ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v for v in (fila[c] for c in columnas)])
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = hoja.dimensions
    for columna, ancho in (("B", 60), ("D", 60)):
        hoja.column_dimensions[columna].width = ancho
    ruta.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta)


def resumen(filas: list[dict], raw1: list, queries: list) -> str:
    estados = Counter(f["SIGA_estado"] for f in filas)
    lineas = [f"Rows: {len(filas)}"] + [f"{e}: {estados[e]}" for e in ESTADOS]
    lineas.append(f"Rows with 2+ options: {sum(f['SIGA_total_opciones'] >= 2 for f in filas)}")
    primera, _ = _por_consulta(raw1, [])
    antes = Counter()
    for f, consulta in zip(filas, queries):
        antes[(estado_pasada1(consulta["q"], primera.get(consulta["q"], [])), f["SIGA_estado"])] += 1
    lineas.append("First pass estado -> new estado:")
    lineas += [f"  {a} -> {b}: {n}" for (a, b), n in sorted(antes.items())]
    return "\n".join(lineas)


def main() -> int:
    rows, queries, raw1, raw2 = cargar_entradas()
    filas = construir_filas(rows, queries, raw1, raw2)
    escribir_xlsx(filas)
    print(f"Wrote {XLSX}")
    print(resumen(filas, raw1, queries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
