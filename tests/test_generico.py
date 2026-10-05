import unittest

from homologador.generico import MAX_DISTANCE, MAX_DISTANCE_RELAJADO, elegir, medidas, penalidad

PLACA = "PLACA DE BLOQUEO LCP DE TITANIO PARA HUMERO DISTAL MEDIAL DE 11 AGUJEROS - X 4.0/3.5 mm   UNIDAD"
VACUNA = "VACUNA CONTRA LA HEPATITIS A 720 UI/0.5 mL 1 DOSIS INYECTABLE"
CATETER_4FR = "CATETER VENOSO CENTRAL 4 FR X 13 cm   UNIDAD"
CATETER_5FR = "CATETER VENOSO CENTRAL TRIPLE LUMEN 5.5F X 13 CM. X UN. CP"


def candidato(item, distance):
    return {"Item": item, "_distance": distance}


class MedidasTest(unittest.TestCase):
    def test_slash_pairs_share_the_unit(self):
        self.assertEqual(medidas(PLACA), {("11", "AGUJEROS"), ("4", "MM"), ("3.5", "MM")})

    def test_dose_and_volume(self):
        self.assertEqual(medidas(VACUNA), {("720", "UI"), ("0.5", "ML")})

    def test_unit_aliases_and_trailing_punctuation(self):
        self.assertEqual(medidas(CATETER_4FR), {("4", "FR"), ("13", "CM")})
        self.assertEqual(medidas(CATETER_5FR), {("5.5", "FR"), ("13", "CM")})
        self.assertEqual(medidas("ACICLOVIR 3% UNG. OFT. X 3.5 GR"), {("3", "%"), ("3.5", "G")})

    def test_numbered_sizes_are_tokens(self):
        self.assertEqual(medidas("HOJA DE BISTURI DESCARTABLE Nº 12   UNIDAD"), {("12", "N")})
        self.assertEqual(medidas("SONDA NASOGASTRICA N° 10   UNIDAD"), {("10", "N")})
        self.assertGreater(penalidad(medidas("HOJA DE BISTURI Nº 12"), medidas("HOJA DE BISTURI Nº 11 - UNIDADES")), 0)

    def test_glove_sizes_are_tokens(self):
        self.assertEqual(medidas("GUANTE PARA EXAMEN DESCARTABLE DE NITRILO SIN POLVO TALLA S   UNIDAD"), {("S", "TALLA")})
        self.assertEqual(medidas("GUANTES DE LATEX DE EXAMINACION NO ESTERIL S CP UNIDADES"), {("S", "TALLA")})
        self.assertEqual(medidas("MANDIL DESCARTABLE TALLA \"XL\" 45GR/M2 ASEPTICO"), {("XL", "TALLA"), ("45", "G")} )

    def test_gauge_number_is_not_also_a_size(self):
        self.assertEqual(medidas("AGUJA HIPODERMICA DESCARTABLE N° 23 G X 1/2\"   UNIDAD"), {("23", "G"), ("1/2", "IN")})
        self.assertEqual(medidas("SONDA DE ASPIRACION N° 10 F   UNIDAD"), {("10", "FR")})

    def test_inches_are_their_own_unit_never_converted(self):
        self.assertEqual(medidas("TUBO DE ASPIRACION 5/16 in X 7/16 in X 3.0 m"), {("5/16", "IN"), ("7/16", "IN"), ("3", "M")})
        self.assertEqual(medidas("TUBO ASPIRACION ESTERIL 5/16\" X 7/16\" X 3 M"), {("5/16", "IN"), ("7/16", "IN"), ("3", "M")})
        self.assertEqual(medidas("AGUJA 22G X 1 1/2''"), {("22", "G"), ("1-1/2", "IN")})
        self.assertNotEqual(medidas("TUBO 7 mm X 11 mm"), medidas("TUBO 5/16 in X 7/16 in"))

    def test_words_starting_like_units_are_not_units(self):
        self.assertEqual(medidas("CATETER TRIPLE 2 LUMEN"), set())

    def test_penalidad_counts_differing_tokens(self):
        self.assertEqual(penalidad(medidas(CATETER_4FR), medidas(CATETER_4FR)), 0)
        self.assertEqual(penalidad(medidas(CATETER_4FR), medidas(CATETER_5FR)), 2)


class ElegirTest(unittest.TestCase):
    def test_number_agreement_beats_closer_distance(self):
        wrong = candidato(CATETER_5FR, 0.30)
        right = candidato("CATETER VENOSO CENTRAL SIMPLE LUMEN 4 FR X 13 CM. X UN. CP", 0.34)
        ranked = elegir(CATETER_4FR, [wrong, right])
        self.assertEqual([c["Item"] for _, c in ranked], [right["Item"], wrong["Item"]])
        self.assertEqual([p for p, _ in ranked], [0, 2])

    def test_distance_breaks_ties(self):
        near, far = candidato("CATETER 4 FR X 13 CM", 0.20), candidato("CATETER 4 FR X 13 CM B", 0.30)
        self.assertEqual([c for _, c in elegir(CATETER_4FR, [far, near])], [near, far])

    def test_candidates_beyond_threshold_are_dropped(self):
        beyond = candidato("CATETER 4 FR X 13 CM", MAX_DISTANCE_RELAJADO + 0.01)
        self.assertEqual(elegir(CATETER_4FR, [beyond]), [])

    def test_numbers_in_the_name_earn_the_relaxed_threshold(self):
        between = candidato("CATETER 4 FR X 13 CM", (MAX_DISTANCE + MAX_DISTANCE_RELAJADO) / 2)
        self.assertEqual(len(elegir(CATETER_4FR, [between])), 1)

    def test_name_without_numbers_keeps_the_strict_threshold(self):
        between = candidato("BRAZALETE DE IDENTIFICACION", (MAX_DISTANCE + MAX_DISTANCE_RELAJADO) / 2)
        self.assertEqual(elegir("BRAZALETE DE TENSIOMETRO ADULTO   UNIDAD", [between]), [])
        self.assertEqual(len(elegir("BRAZALETE DE TENSIOMETRO ADULTO", [dict(between, _distance=MAX_DISTANCE - 0.01)])), 1)

    def test_threshold_sits_between_related_and_unrelated_rows(self):
        # Observed on the real catalog: related catheters/needles start at 0.275, the first unrelated
        # plate/screw -> suture neighbours at 0.36 and above.
        self.assertTrue(0.275 < MAX_DISTANCE < 0.36)
        self.assertTrue(MAX_DISTANCE < MAX_DISTANCE_RELAJADO <= 0.45)


if __name__ == "__main__":
    unittest.main()
