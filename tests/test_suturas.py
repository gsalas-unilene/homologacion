import csv
import tempfile
import unittest
from pathlib import Path

from homologador.suturas import cargar_indice, emparejar, indexar


def row(coditem, codsut, item):
    return {"Coditem": coditem, "CodSut": codsut, "Item": item, "Agrupador": "01. SUTURAS"}


SEDA = "SEDA NEGRA TRENZADA 3/0 AGUJA "
ROWS = [
    row("PSTSN02412", "SDST030TC25007512ASCE", SEDA + "3/8 CÍRCULO CORTANTE 25 MM X 75 CM SD"),
    row("PSTSN02413", "SDST030TC25007536ASCE", SEDA + "3/8 CÍRCULO CORTANTE 25 MM X 75 CM SD"),
    row("PSTSN04770", "CQST030TC25007524ASCE", SEDA + "3/8 CÍRCULO CORTANTE 25 MM X 75 CM CQ"),
    row("PSTSN06519", "SDST030TC22007512ASCE", SEDA + "3/8 CÍRCULO CORTANTE 22 MM X 75 CM SD"),
    row("PSTSN02402", "SDST030TC20008036ASCE", SEDA + "3/8 CÍRCULO CORTANTE 20 MM X 80 CM SD"),
    row("PSTSN05482", "CQST030MR15007524ASCE", SEDA + "1/2 CÍRCULO REDONDA 15 MM X 75 CM CQ"),
    row("PSTSN06300", "CQST030XM10M07524ASCE", "SEDA NEGRA TRENZADA 3/0 MULTIEMPAQUE 10 HEBRAS X 75 CM   CQ"),
    row("PSTSN04018", "VSST030TC25007512ASCE", SEDA + "3/8 CÍRCULO CORTANTE 25 MM X 75 CM VS"),
    row("PSTAA00308", "SDAA030TC19007036ASCE", "ÁCIDO POLIGLICÓLICO ANTIBACTERIAL 3/0 AGUJA 3/8 CÍRCULO CORTANTE 19 MM X 70 CM SD"),
    row("PSOPG00113", "SDAG060QE07604512BSCE", "POLIGLACTIN 6/0 AGUJA 1/4 CÍRCULO ESPATULADA 7.6 MM X 45 CM C/2A  SD"),
    row("PSTCR01611", "SDCC010TC40009012ASCE", "CATGUT CRÓMICO 0 AGUJA 3/8 CÍRCULO CORTANTE 40 MM X 90 CM SD"),
]
INDICE = indexar(ROWS)


def ejemplo(nombre, indice=INDICE):
    return emparejar(nombre, indice)


class EmparejarTest(unittest.TestCase):
    def test_exact_match_prefers_sd_then_code_order_and_lists_alternatives(self):
        r = ejemplo("SUTURA SEDA NEGRA TRENZADA 3/0 C/A 3/8 CIRCULO CORTANTE 25 mm X 75 cm   UNIDAD")
        self.assertEqual((r["tier"], r["Coditem"], r["marca"], r["CodSut"]), ("exacto", "PSTSN02412", "SD", "SDST030TC25007512ASCE"))
        self.assertEqual((r["diferencias"], r["alt_2"], r["alt_3"]), ("", "PSTSN02413", "PSTSN04770"))
        self.assertEqual(r["Agrupador"], "01. SUTURAS")

    def test_nearest_needle_then_thread_length_is_chosen_and_listed(self):
        r = ejemplo("SUTURA SEDA NEGRA TRENZADA 3/0 C/A 3/8 CIRCULO CORTANTE 22 mm X 80 cm   UNIDAD")
        self.assertEqual((r["tier"], r["Coditem"], r["diferencias"]), ("probable", "PSTSN06519", "long_hebra:80!=75cm"))

    def test_needle_length_difference_is_reported(self):
        r = ejemplo("SUTURA SEDA NEGRA TRENZADA 3/0 C/A 3/8 CIRCULO CORTANTE 15 mm X 75 cm   UNIDAD")
        self.assertEqual((r["tier"], r["diferencias"]), ("probable", "long_aguja:15!=20mm; long_hebra:75!=80cm"))
        self.assertEqual(r["Coditem"], "PSTSN02402")  # 20 mm is the nearest needle (22 mm is 7 away)

    def test_other_brand_is_never_a_candidate(self):
        solo_vs = indexar([ROWS[7]])
        r = ejemplo("SUTURA SEDA NEGRA TRENZADA 3/0 C/A 3/8 CIRCULO CORTANTE 25 mm X 75 cm   UNIDAD", solo_vs)
        self.assertEqual((r["tier"], r["Coditem"], r["marca"], r["CodSut"], r["diferencias"]), ("sin_equivalente", "", "", "", ""))

    def test_cq_candidate_for_a_curvature_only_cq_has(self):
        r = ejemplo("SUTURA SEDA NEGRA TRENZADA 3/0 C/A 1/2 CIRCULO REDONDA 15 mm X 75 cm   UNIDAD")
        self.assertEqual((r["tier"], r["Coditem"], r["marca"]), ("exacto", "PSTSN05482", "CQ"))

    def test_same_family_and_calibre_with_other_point_is_review(self):
        r = ejemplo("SUTURA SEDA NEGRA TRENZADA 3/0 C/A 3/8 CIRCULO REDONDA 25 mm X 75 cm   UNIDAD")
        self.assertEqual((r["tier"], r["Coditem"]), ("revisar", "PSTSN02412"))
        self.assertEqual(r["diferencias"], "punta:redonda!=cortante")

    def test_unstated_needle_point_is_review_not_mismatch(self):
        r = ejemplo("SUTURA SEDA NEGRA TRENZADA 3/0 C/A 3/8 CIRCULO 25 mm X 75 cm   UNIDAD")
        self.assertEqual((r["tier"], r["diferencias"]), ("revisar", "punta:?!=cortante"))

    def test_unstated_calibre_searches_the_family_and_is_review(self):
        r = ejemplo("SUTURA CATGUT CROMICO   UNIDAD")
        self.assertEqual((r["tier"], r["Coditem"]), ("revisar", "PSTCR01611"))

    def test_no_item_with_that_family_and_calibre(self):
        r = ejemplo("SUTURA SEDA NEGRA TRENZADA 12/0 C/A 3/8 CIRCULO CORTANTE 25 mm X 75 cm   UNIDAD")
        self.assertEqual((r["tier"], r["Coditem"], r["Item"]), ("sin_equivalente", "", ""))

    def test_variant_difference_gives_probable(self):
        r = ejemplo("SUTURA ACIDO POLIGLICOLICO 3/0 C/A 3/8 CIRCULO CORTANTE 19 mm X 70 cm   UNIDAD")
        self.assertEqual((r["tier"], r["Coditem"], r["diferencias"]), ("probable", "PSTAA00308", "variante:-!=antibacterial"))

    def test_double_needle_matches_class_b(self):
        r = ejemplo("SUTURA ACIDO POLIGLACTIN 6/0 C/DOBLE AGUJA 1/4 CIRCULO ESPATULADA 7.6 mm X 45 cm   UNIDAD")
        self.assertEqual((r["tier"], r["Coditem"], r["diferencias"]), ("exacto", "PSOPG00113", ""))

    def test_single_needle_request_flags_a_double_needle_item(self):
        r = ejemplo("SUTURA ACIDO POLIGLACTIN 6/0 C/A 1/4 CIRCULO ESPATULADA 7.6 mm X 45 cm   UNIDAD")
        self.assertEqual((r["tier"], r["diferencias"]), ("probable", "agujas:1!=2"))

    def test_multipack_matches_on_strands(self):
        r = ejemplo("SUTURA SEDA NEGRA TRENZADA MULTIEMPAQUE 3/0 S/A 10 HEBRAS X 75 cm   UNIDAD")
        self.assertEqual((r["tier"], r["Coditem"], r["diferencias"]), ("exacto", "PSTSN06300", ""))


class IndiceTest(unittest.TestCase):
    def test_only_sd_and_cq_suture_items_are_indexed(self):
        self.assertEqual(sum(len(v) for v in indexar(ROWS).values()), len(ROWS) - 1)  # the VS row is out
        non_suture = dict(ROWS[0], Agrupador="13. OTROS", Coditem="X1")
        self.assertEqual(sum(len(v) for v in indexar([non_suture]).values()), 0)

    def test_cargar_indice_reads_the_items_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "items.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, ["Coditem", "CodSut", "Item", "Agrupador"])
                writer.writeheader()
                writer.writerows(ROWS)
            self.assertEqual(emparejar("SUTURA SEDA NEGRA TRENZADA 3/0 C/A 3/8 CIRCULO CORTANTE 25 mm X 75 cm", cargar_indice(path))["tier"], "exacto")


if __name__ == "__main__":
    unittest.main()
