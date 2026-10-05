import unittest

from homologador.generico import MAX_DISTANCE, MAX_DISTANCE_RELAJADO, compatibles, elegir, medidas, penalidad

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

    def test_half_sizes_are_distinct_from_whole_sizes(self):
        self.assertEqual(medidas("GUANTE QUIRURGICO ESTERIL EMPAQUE INDIV. Nº 7 1/2 PUÑO LARGO   PAR"), {("7-1/2", "N")})
        self.assertEqual(medidas("GUANTE QUIRURGICO ESTERIL EMPAQUE INDIV. Nº 7 PUÑO LARGO"), {("7", "N")})

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


class CompatiblesTest(unittest.TestCase):
    def assertPair(self, name, item, expected):
        self.assertEqual(compatibles(name, item), expected, f"{name} | {item}")

    def test_junk_pairs_from_the_full_run_are_rejected(self):
        for name, item in [
            ("ANTIFUNGIGRAMA AUTOMATIZADO PARA LEVADURAS - X DETERMINACION UNIDAD", "TRAZANTO SISTEMA AUTOMÁTICO DE TRAZABILIDAD"),
            ("TRLIGLICERIDO ENZIMATICO AUTOMATIZADO - X DETERMINACION UNIDAD", "TRAZANTO SISTEMA AUTOMÁTICO DE TRAZABILIDAD"),
            ("BRAZALETE Y PERA PARA TENSIOMETRO   UNIDAD", "BRAZALETE DE IDENTIFICACION ROSADO X 01 UND"),
            ("BRAZALETE DE TENSIOMETRO LACTANTE   UNIDAD", "BRAZALETE DE IDENTIFICACION CELESTE X 01 UND"),
            ("KIT PARA DOSAJE DE LA PROTEINA S FUNCIONAL - X DETERMINACION UNIDAD", "HISOPO PARA DETECCIÓN DE PROTEINAS - PRO1 ENDO CAJA X 20"),
            ("RESPIRADOR DE CARA COMPLETA DE ELASTOMERO TALLA L   UNIDAD", "GUANTES DE LATEX DE EXAMINACION NO ESTERIL L CP UNIDADES"),
            ("JUEGO DE ESPEJOS BUCALES CON MANGO SIN AUMENTO X 12 PIEZAS   UNIDAD", "CERA PARA HUESO R CAJA X 12 UND - SUTUMED"),
        ]:
            self.assertPair(name, item, False)

    def test_contrastive_qualifiers_are_rejected(self):
        for name, item in [
            ("CATETER VENOSO CENTRAL DOBLE LUMEN 5.5 FR x 13 cm   UNIDAD", "CATETER VENOSO CENTRAL TRIPLE LUMEN 5.5F X 13 CM. X UN. CP"),
            ("CATETER VENOSO CENTRAL UN LUMEN 14 G X 16 cm   UNIDAD", "CATETER VENOSO CENTRAL DOBLE LUMEN 14G X 16 CM. X UN. CP"),
            ("MANDIL DESCARTABLE NO ESTERIL TALLA M   UNIDAD", "MANDIL DESCARTABLE ESTÉRIL TALLA M - CP"),
            ("MASCARA REINHALATORIA DE OXIGENO PEDIATRICA", "MÁSCARA DE OXÍGENO DE NO REINHALACIÓN PEDIÁTRICA ASÉPTICO"),
            ("GUANTE PARA EXAMEN SIN POLVO TALLA M", "GUANTES DE EXAMINACION CON POLVO TALLA M"),
        ]:
            self.assertPair(name, item, False)

    def test_good_pairs_are_kept(self):
        for name, item in [
            ("CATETER VENOSO CENTRAL TRIPLE LUMEN 7 FR X 20 cm   UNIDAD", "CATETER VENOSO CENTRAL TRIPLE LUMEN 7F X 20 CM. X UN. CP"),
            ("CATETER VENOSO CENTRAL UN LUMEN 14 G X 16 cm   UNIDAD", "CATETER VENOSO CENTRAL SIMPLE LUMEN 14G X 16 CM. X UN. CP"),
            ("CATETER VENOSO CENTRAL 4 FR X 13 cm   UNIDAD", "CATETER VENOSO CENTRAL DOBLE LUMEN 4F X 13 CM. X UN. CP"),
            ("HOJA DE BISTURI DESCARTABLE Nº 21   UNIDAD", "HOJA DE BISTURI Nº 21 - UNIDADES"),
            ("ESPONJA HEMOSTATICA DE COLAGENO 3 cm X 5 cm   UNIDAD", "ESPONJA HEMOSTÁTICA 3 CM. X 5 CM. VE"),
            ("ESPONJA HEMOSTATICA DE COLAGENO 10 cm X 10 cm   UNIDAD", "HEMOCOLAGEN, ESPONJA HEMOSTÁTICA DE COLÁGENO ABSORBENTE 10 C"),
            ("TUBO DE ASPIRACION TRANSPARENTE 5/16 in X 7/16 in X 3.0 m   UNIDAD", "TUBO ASPIRACION ESTERIL 5/16\" X 7/16\" X 3 M"),
            ("MANDIL DESCARTABLE ESTERIL TALLA M   UNIDAD", "MANDIL DESCARTABLE ESTÉRIL TALLA M - CP"),
            ("AGUJA DE PUNCION LUMBAR 22 G X 3 1/2\"   UNIDAD", "AGUJA ESPINAL PUNTA LÁPIZ 22G X 3 1/2'' X UN. CP"),
            ("SET DE ANESTESIA EPIDURAL CON AGUJA Nº 18 G X 3 1/2\"   UNIDAD", "AGUJA EPIDURAL 18G X 3 1/2'' X CAJA DE 50 UN. CP"),
            ("GUANTE PARA EXAMEN DESCARTABLE TALLA M   UNIDAD", "GUANTES DE LATEX DE EXAMINACION NO ESTERIL M CP UNIDADES"),
            ("GUANTE QUIRURGICO ESTERIL EMPAQUE INDIV. Nº 7 PUÑO LARGO (PAR)", "GUANTES QUIRURGICOS DE LATEX ESTERIL Nº 7.0 CP"),
            ("APOSITO DE HIDROGEL CON PLATA IONICA 10 cm X 10 cm   UNIDAD", "APÓSITO DE FIBRA GELIFICANTE CON PLATA EXTRA 10 X 10 CM. CAJ"),
        ]:
            self.assertPair(name, item, True)

    def test_names_without_numbers_need_two_shared_words(self):
        for name, item in [
            ("BRAZALETE DE IDENTIFICACION PEDIATRICO   UNIDAD", "BRAZALETE DE IDENTIFICACION CELESTE X 01 UND"),
            ("MASCARA DE OXIGENO CON RESERVORIO NEONATAL   UNIDAD", "GAMED MÁSCARA DE OXÍGENO SIMPLE NEO NATAL ASÉPTICO"),
            ("MASCARA DE OXIGENO CON BOLSA DE RESERVORIO NO REINHALATORIA", "GAMED MÁSCARA DE OXÍGENO DE NO REINHALACIÓN PEDIÁTRICA ASÉPT"),
            ("SET DE IRRIGACION EN Y PARA CIRUGIA LAPAROSCOPICA   SET", "SET DE CANULAS PARA IRRIGACION"),
            ("INDICADOR MULTIPARAMETRO (INTEGRADOR) DE ESTERILIZACION A VAPOR  X 480 UNIDAD", "INDICADOR MULTIPARÁMETRO DE VAPOR - CD29 CAJA X 500"),
        ]:
            self.assertPair(name, item, True)


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
        name = "BRAZALETE DE IDENTIFICACION PEDIATRICO   UNIDAD"
        between = dict(between, Item="BRAZALETE DE IDENTIFICACION CELESTE X 01 UND")
        self.assertEqual(elegir(name, [between]), [])
        self.assertEqual(len(elegir(name, [dict(between, _distance=MAX_DISTANCE - 0.01)])), 1)

    def test_incompatible_words_drop_the_candidate(self):
        wristband = candidato("BRAZALETE DE IDENTIFICACION ROSADO X 01 UND", 0.20)
        self.assertEqual(elegir("BRAZALETE Y PERA PARA TENSIOMETRO   UNIDAD", [wristband]), [])

    def test_threshold_sits_between_related_and_unrelated_rows(self):
        # Observed on the real catalog: related catheters/needles start at 0.275, the first unrelated
        # plate/screw -> suture neighbours at 0.36 and above.
        self.assertTrue(0.275 < MAX_DISTANCE < 0.36)
        self.assertTrue(MAX_DISTANCE < MAX_DISTANCE_RELAJADO <= 0.45)


if __name__ == "__main__":
    unittest.main()
