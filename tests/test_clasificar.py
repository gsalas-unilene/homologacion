import unittest

from homologador.clasificar import clasificar, es_sutura
from homologador.generico import MAX_DISTANCE
from homologador.suturas import indexar

SEDA = "SUTURA SEDA NEGRA TRENZADA 3/0 C/A 3/8 CIRCULO CORTANTE 25 mm X 75 cm   UNIDAD"
CATETER = "CATETER VENOSO CENTRAL 4 FR X 13 cm   UNIDAD"


def candidato(coditem, item, distance, agrupador="01. SUTURAS"):
    return {"row_id": coditem, "Coditem": coditem, "Item": item, "Agrupador": agrupador, "_distance": distance}




class SutureDispatchTest(unittest.TestCase):
    def test_suture_rows_use_the_structured_index_and_ignore_vector_candidates(self):
        indice = indexar([{"Coditem": "PSTSN02412", "CodSut": "SDST030TC25007512ASCE", "Agrupador": "01. SUTURAS",
                           "Item": "SEDA NEGRA TRENZADA 3/0 AGUJA 3/8 CÍRCULO CORTANTE 25 MM X 75 CM SD"}])
        result = clasificar(SEDA, [], indice)
        self.assertEqual((result["tier"], result["Coditem"], result["marca"]), ("exacto", "PSTSN02412", "SD"))

    def test_generic_rows_leave_the_new_columns_empty(self):
        match = candidato("C1", "CATETER VENOSO CENTRAL SIMPLE LUMEN 4 FR X 13 CM. X UN. CP", 0.30, "13. OTROS")
        result = clasificar(CATETER, [match])
        self.assertEqual(result["tier"], "revisar")
        self.assertEqual((result.get("marca", ""), result.get("CodSut", ""), result.get("diferencias", "")), ("", "", ""))


class RoutingTest(unittest.TestCase):
    def test_only_named_sutures_with_material_take_the_suture_path(self):
        self.assertTrue(es_sutura(SEDA))
        self.assertFalse(es_sutura(CATETER))
        self.assertFalse(es_sutura("SUTURA CON PUAS UNIDIRECCIONAL MONOFILAMENTO VERDE 0 C/A 1/2 CIRCULO"))


class GenericTierTest(unittest.TestCase):
    def test_agreeing_numbers_within_threshold_is_review(self):
        match = candidato("C1", "CATETER VENOSO CENTRAL SIMPLE LUMEN 4 FR X 13 CM. X UN. CP", 0.30, "13. OTROS")
        other = candidato("C2", "CATETER VENOSO CENTRAL TRIPLE LUMEN 5.5F X 13 CM. X UN. CP", 0.28, "13. OTROS")
        result = clasificar(CATETER, [other, match])
        self.assertEqual((result["tier"], result["Coditem"], result["distance"]), ("revisar", "C1", 0.30))
        self.assertEqual(result["score"], 0)

    def test_disagreeing_numbers_is_no_equivalent_and_keeps_nearest_distance(self):
        other = candidato("C2", "CATETER VENOSO CENTRAL TRIPLE LUMEN 5.5F X 13 CM. X UN. CP", 0.28, "13. OTROS")
        result = clasificar(CATETER, [other])
        self.assertEqual((result["tier"], result["Coditem"], result["Item"]), ("sin_equivalente", "", ""))
        self.assertEqual(result["distance"], 0.28)

    def test_beyond_threshold_is_no_equivalent(self):
        far = candidato("C1", "CATETER 4 FR X 13 CM", 0.6, "13. OTROS")
        self.assertEqual(clasificar(CATETER, [far])["tier"], "sin_equivalente")

    def test_suture_without_known_material_uses_generic_strategy(self):
        barbed = "SUTURA CON PUAS UNIDIRECCIONAL MONOFILAMENTO VERDE 0 C/A 1/2 CIRCULO PUNTA CILINDRICA 37 mm X 30 cm"
        match = candidato("B1", "SUTURA CON PUAS 37 MM X 30 CM", 0.30)
        self.assertEqual(clasificar(barbed, [match])["tier"], "revisar")


if __name__ == "__main__":
    unittest.main()
