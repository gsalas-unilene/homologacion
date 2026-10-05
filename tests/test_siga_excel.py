import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import siga_excel

MUESTRA = json.loads((Path(__file__).parent / "fixtures" / "siga_muestra.json").read_text(encoding="utf-8"))
HOMOLOGACION = ["CodigoMed", "NombreMed", "Coditem", "Item", "Agrupador", "tier", "distance", "score", "alt_2", "alt_3",
                "marca", "CodSut", "diferencias"]


def entradas(registros):
    rows, queries, raw1, raw2 = [], [], [], []
    for i, r in enumerate(registros):
        q = r["nombre"].strip()
        rows.append({**{c: "" for c in HOMOLOGACION}, "CodigoMed": r["cod"], "NombreMed": r["nombre"], "tier": "revisar"})
        queries.append({"i": i, "cod": r["cod"], "q": q})
        raw1.append({"q": q, "http": 200, "status": "", "rows": r["raw1"]})
        raw2 += [{"q": q, "v": v["v"], "status": "", "total": len(v["rows"]), "rows": v["rows"]} for v in r["raw2"]]
    return rows, queries, raw1, raw2


def registro(inicio):
    return next(r for r in MUESTRA if r["nombre"].startswith(inicio))


class ConstruirFilasTest(unittest.TestCase):
    def test_columns_keep_the_homologation_ones_and_add_the_siga_ones(self):
        filas = siga_excel.construir_filas(*entradas([registro("SUTURA SEDA NEGRA TRENZADA 3/0 C/A 3/8 CIRCULO CORTANTE 30 mm")]))
        self.assertEqual(list(filas[0]), HOMOLOGACION + [
            "SIGA_estado", "SIGA_puntaje", "SIGA_codigo_1", "SIGA_descripcion_1", "SIGA_diferencias",
            "SIGA_codigo_2", "SIGA_codigo_3", "SIGA_codigo_4", "SIGA_codigo_5", "SIGA_alternativas", "SIGA_total_opciones"])

    def test_values_for_an_exact_row_a_row_with_alternatives_and_one_without_result(self):
        filas = siga_excel.construir_filas(*entradas([
            registro("SUTURA SEDA NEGRA TRENZADA 3/0 C/A 3/8 CIRCULO CORTANTE 30 mm"),
            registro("SUTURA ACIDO POLIGLACTIN 1/0 C/A 1/2 CIRCULO REDONDA 36 mm"),
            registro("SUTURA DE ACIDO POLIGLACTIN (VICRYL"),
        ]))
        exacto, mejor, nada = filas
        self.assertEqual((exacto["SIGA_estado"], exacto["SIGA_puntaje"], exacto["SIGA_codigo_1"], exacto["SIGA_total_opciones"]),
                         ("exacto", 100, "495700580110", 1))
        self.assertEqual((exacto["SIGA_codigo_2"], exacto["SIGA_alternativas"]), ("", ""))
        self.assertEqual((mejor["SIGA_estado"], mejor["SIGA_codigo_1"], mejor["SIGA_diferencias"]),
                         ("mejor_coincidencia", "495701350512", "long_aguja:36!=36.4mm"))
        self.assertEqual(mejor["SIGA_total_opciones"], 7)
        # Options 2..5 are shown, with their descriptions in the alternatives column.
        self.assertTrue(all(mejor[f"SIGA_codigo_{n}"] for n in (2, 3, 4, 5)))
        self.assertEqual(mejor["SIGA_alternativas"].count(" | "), 3)
        self.assertTrue(mejor["SIGA_alternativas"].startswith(f"{mejor['SIGA_codigo_2']}: SUTURA ACIDO POLIGLACTIN 1/0"))
        self.assertEqual((nada["SIGA_estado"], nada["SIGA_codigo_1"], nada["SIGA_descripcion_1"], nada["SIGA_total_opciones"]),
                         ("sin_resultado", "", "", 0))

    def test_rows_and_queries_that_do_not_line_up_are_rejected(self):
        rows, queries, raw1, raw2 = entradas([registro("HOJA DE BISTURI")])
        queries[0]["cod"] = "otro"
        with self.assertRaises(ValueError):
            siga_excel.construir_filas(rows, queries, raw1, raw2)

    def test_failed_first_pass_records_do_not_count_as_results(self):
        rows, queries, raw1, raw2 = entradas([registro("HOJA DE BISTURI")])
        raw1 = [{"q": queries[0]["q"], "http": 401, "rows": [["1", "SE DESCARTA"]]}] + raw1
        self.assertEqual(siga_excel.construir_filas(rows, queries, raw1, raw2)[0]["SIGA_estado"], "exacto")


class PasadaUnoTest(unittest.TestCase):
    def test_first_pass_estado(self):
        q = "HOJA DE BISTURI DESCARTABLE Nº 12"
        self.assertEqual(siga_excel.estado_pasada1(q, [["1", "HOJA DE BISTURI DESCARTABLE N° 12"]]), "exacto")
        self.assertEqual(siga_excel.estado_pasada1(q, [["1", "OTRA COSA"]]), "unico")
        self.assertEqual(siga_excel.estado_pasada1(q, [["1", "OTRA"], ["2", "COSA"]]), "multiple")
        self.assertEqual(siga_excel.estado_pasada1(q, []), "sin_resultado")


@unittest.skipUnless(importlib.util.find_spec("openpyxl"), "openpyxl is only available through `uv run --with openpyxl`")
class XlsxTest(unittest.TestCase):
    def test_sheet_header_freeze_filter_and_illegal_characters(self):
        import openpyxl

        filas = siga_excel.construir_filas(*entradas([registro("HOJA DE BISTURI")]))
        filas[0]["NombreMed"] = "HOJA\x01 DE\x0b BISTURI"
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "final.xlsx"
            siga_excel.escribir_xlsx(filas, ruta)
            hoja = openpyxl.load_workbook(ruta).active
        self.assertEqual(hoja.title, "homologacion_siga")
        self.assertEqual(hoja.freeze_panes, "A2")
        self.assertIsNotNone(hoja.auto_filter.ref)
        self.assertEqual([c.value for c in hoja[1]], list(filas[0]))
        self.assertEqual(hoja.cell(row=2, column=2).value, "HOJA DE BISTURI")


if __name__ == "__main__":
    unittest.main()
