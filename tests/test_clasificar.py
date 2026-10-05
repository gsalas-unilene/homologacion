import unittest

from homologador.clasificar import clasificar
from homologador.generico import MAX_DISTANCE

SEDA = "SUTURA SEDA NEGRA TRENZADA 3/0 C/A 3/8 CIRCULO CORTANTE 25 mm X 75 cm   UNIDAD"
CATETER = "CATETER VENOSO CENTRAL 4 FR X 13 cm   UNIDAD"


def candidato(coditem, item, distance, agrupador="01. SUTURAS"):
    return {"row_id": coditem, "Coditem": coditem, "Item": item, "Agrupador": agrupador, "_distance": distance}


SEDA_2_0 = candidato("A1", "SEDA NEGRA TRENZADA 2/0 AGUJA 3/8 CÍRCULO CORTANTE 25 MM X 75 CM CP", 0.20)
SEDA_3_0 = candidato("A2", "SEDA NEGRA TRENZADA 3/0 AGUJA 3/8 CÍRCULO CORTANTE 25 MM X 75 CM CP", 0.25)
SEDA_3_0_REDONDA = candidato("A3", "SEDA NEGRA TRENZADA 3/0 AGUJA 3/8 CÍRCULO REDONDA 25 MM X 75 CM CP", 0.26)
NYLON_3_0 = candidato("A4", "NYLON NEGRO MONOFILAMENTO 3/0 AGUJA 3/8 CÍRCULO CORTANTE 25 MM X 75 CM SD", 0.22)


class SutureTierTest(unittest.TestCase):
    def test_exact_attributes_win_over_closer_vector_and_list_alternatives(self):
        result = clasificar(SEDA, [SEDA_2_0, NYLON_3_0, SEDA_3_0, SEDA_3_0_REDONDA])
        self.assertEqual(result["tier"], "exacto")
        self.assertEqual((result["Coditem"], result["Agrupador"]), ("A2", "01. SUTURAS"))
        self.assertEqual(result["distance"], 0.25)
        self.assertGreater(result["score"], 0)
        self.assertEqual((result["alt_2"], result["alt_3"]), ("A3", "A1"))

    def test_exact_is_kept_beyond_the_distance_threshold(self):
        far = dict(SEDA_3_0, _distance=MAX_DISTANCE + 0.05)
        self.assertEqual(clasificar(SEDA, [far])["tier"], "exacto")

    def test_same_family_with_different_attribute_is_review(self):
        result = clasificar(SEDA, [SEDA_2_0, NYLON_3_0, SEDA_3_0_REDONDA])
        self.assertEqual(result["tier"], "revisar")
        self.assertEqual(result["Coditem"], "A3")

    def test_other_material_only_is_no_equivalent(self):
        result = clasificar(SEDA, [NYLON_3_0])
        self.assertEqual(result["tier"], "sin_equivalente")
        self.assertEqual(result["Coditem"], "")

    def test_review_candidate_beyond_threshold_is_no_equivalent(self):
        far = dict(SEDA_2_0, _distance=MAX_DISTANCE + 0.05)
        self.assertEqual(clasificar(SEDA, [far])["tier"], "sin_equivalente")


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
