import unittest

from homologador.atributos import core_exact, parse, parse_item, score

SEDA_MINSA = "SUTURA SEDA NEGRA TRENZADA 3/0 C/A 3/8 CIRCULO CORTANTE 25 mm X 75 cm   UNIDAD"
PGA_ITEM = "ÁCIDO POLIGLICÓLICO 0 AGUJA 3/8 CÍRCULO CORTANTE 35 MM X 70 CM CP"


def fields(text, *keys):
    attrs = parse(text)
    return tuple(attrs[key] for key in keys)


class ParseTest(unittest.TestCase):
    def test_full_needle_suture(self):
        self.assertEqual(
            fields(SEDA_MINSA, "mat", "gauge", "curv", "type", "mm", "cm", "needles"),
            ("SEDA", "3/0", "3/8", "CORTANTE", "25", "75", 1),
        )

    def test_polyglactin_without_final_a(self):
        text = "SUTURA ACIDO POLIGLACTIN 2/0 C/A 1/2 CIRCULO REDONDA 20 mm X 70 cm   UNIDAD"
        self.assertEqual(fields(text, "mat", "gauge", "curv", "type"), ("PGLA", "2/0", "1/2", "REDONDA"))

    def test_polypropylene_spelling_and_double_needle(self):
        text = "SUTURA POLIPROPILEN AZUL MONOFILAMENTO 6/0 C/2A 3/8 CIRCULO REDONDA 13 mm X 75 cm   UNIDAD"
        self.assertEqual(fields(text, "mat", "needles"), ("POLIPROPILENO", 2))

    def test_double_needle_spatula(self):
        text = "SUTURA ACIDO POLIGLACTIN 7/0 C/DOBLE AGUJA 3/8 CIRCULO ESPATULADA 6.5 mm X 45 cm  SOBRE X UNIDAD UNIDAD"
        self.assertEqual(fields(text, "type", "mm", "needles"), ("ESPATULADA", "6.5", 2))

    def test_no_needle_multiempaque(self):
        text = "SUTURA SEDA NEGRA TRENZADA MULTIEMPAQUE 2/0 S/A X 75 cm   UNIDAD"
        self.assertEqual(fields(text, "mat", "gauge", "cm", "needles"), ("SEDA", "2/0", "75", 0))

    def test_linen_with_strands_is_not_gauge(self):
        text = "SUTURA LINO MULTIEMPAQUE 4/0 S/A 10 HEBRAS X 75 cm   UNIDAD"
        self.assertEqual(fields(text, "mat", "gauge", "needles"), ("LINO", "4/0", 0))

    def test_abbreviated_curvature_and_type(self):
        text = "SUTURA DE SEDA NEGRA TRENZADA NO 4/0 C/A  1/2 CR 20MM UNIDAD"
        self.assertEqual(
            fields(text, "gauge", "curv", "type", "mm"), ("4/0", "1/2", "REDONDA", "20")
        )

    def test_integer_gauge_before_fraction_curvature(self):
        text = "SUTURA NYLON AZUL MONOFILAMENTO  1 1/2 CC 25 UNIDAD"
        self.assertEqual(fields(text, "mat", "gauge", "curv", "type"), ("NYLON", "1", "1/2", "CORTANTE"))

    def test_gauge_with_numero_sign_and_replacement_char(self):
        text = "SUTURA DE ACIDO POLIGLICOLICO N�4 C/A 1/2 CIRCULO REDONDO 15 mm X 70 cm   UNIDAD"
        self.assertEqual(fields(text, "mat", "gauge", "type"), ("PGA", "4", "REDONDA"))

    def test_plain_integer_gauge(self):
        text = "SUTURA ACIDO POLIGLACTIN 4 C/A 1/2 CIRCULO REDONDA 30 mm X 70 cm   UNIDAD"
        self.assertEqual(fields(text, "gauge", "curv"), ("4", "1/2"))

    def test_gauge_zero_before_curvature(self):
        text = "SUTURA SEDA NEGRA TRENZADA 0 3/8 C/A REDONDA 35 mm X 75 cm   UNIDAD"
        self.assertEqual(fields(text, "gauge", "curv", "type"), ("0", "3/8", "REDONDA"))

    def test_medio_circulo_and_glued_curvature(self):
        self.assertEqual(
            fields("SUTURA CATGUT  CROMICO 3/0 C/A 1/2 MEDIO CIRCULO REDONDA 15 mm X 70 cm", "mat", "curv"),
            ("CATGUT CROMICO", "1/2"),
        )
        self.assertEqual(
            fields("SUTURA CATGUT CROMICO 2/0 C/A1/2 CIRCULO REDONDA 30 mm X 150 cm", "curv"), ("1/2",)
        )

    def test_stainless_steel_and_ultra_high_polyethylene(self):
        self.assertEqual(
            fields("SUTURA DE ACERO INOXIDABLE MONOFILAMENTO 5 C/A 1/2 CIRCULO REDONDA 50 mm X 180 cm", "mat", "gauge"),
            ("ACERO", "5"),
        )
        self.assertEqual(
            fields("SUTURA DE POLIETILENO MONOFILAMENTO 2 C/A 1/2 CIRCULO CORTANTE 26.5 mm x 97 cm", "mat", "gauge", "mm"),
            ("POLIETILENO", "2", "26.5"),
        )

    def test_glued_tokens_and_ordinal_sign(self):
        text = "SUTURA NYLON AZUL MONOFILAMENTO NO 2/0 C/A  1/2CR 40MM UNIDAD"
        self.assertEqual(fields(text, "curv", "type", "mm"), ("1/2", "REDONDA", "40"))
        self.assertEqual(
            fields("SUTURA DE POLIETILENO BLANCO Nº 2 C/A 26 mm X 90 cm   UNIDAD", "mat", "gauge"),
            ("POLIETILENO", "2"),
        )
        self.assertEqual(fields("SUTURA CATGUT CROMICO 1  S/A150 cm   UNIDAD", "gauge", "needles"), ("1", 0))

    def test_cylindrical_spatula_and_straight_needles(self):
        self.assertEqual(
            fields("SUTURA DE POLIGLICONATO 3/0 C/A 1/2 CIRCULO PUNTA CILINDRICA - 26 mm X 23 cm", "mat", "type"),
            ("POLIGLICONATO", "CILINDRICA"),
        )
        self.assertEqual(
            fields("SUTURA ACIDO POLIGLACTIN 7/0 C/A ESPATULA 3/8 CIRCULAR X 6.5 mm X 45 cm", "type", "mm"),
            ("ESPATULADA", "6.5"),
        )
        self.assertEqual(
            fields("SUTURA DE ACERO PARA MARCAPASO 2/0 C/A 1/2 CIRCULO RECTA 26 mm X 60 cm", "mat", "type"),
            ("ACERO", "RECTA"),
        )

    def test_barbed_suture_gets_gauge_without_material(self):
        text = "SUTURA CON PUAS UNIDIRECCIONAL MONOFILAMENTO VERDE 0 C/A 1/2 CIRCULO PUNTA CILINDRICA 37 mm X 30 cm"
        self.assertEqual(fields(text, "gauge", "type"), ("0", "CILINDRICA"))

    def test_vulgar_fraction_sign_and_leading_two_needle_marker(self):
        self.assertEqual(fields("SUTURA CON PUAS UNIDIRECCIONAL MONOFILAMENTO VIOLETA 2/0 C/A ½ CIRCULO PUNTA REDONDA 27 mm X 25 cm", "curv"), ("1/2",))
        self.assertEqual(fields("SUTURA DE POLIPROPILENO 6/0 2C/A 3/8 CIRCULO REDONDA 13 mm x 75 cm   UNIDAD", "mat", "needles"), ("POLIPROPILENO", 2))

    def test_unparseable_text_yields_none(self):
        attrs = parse("VACUNA CONTRA LA HEPATITIS A 720 UI/0.5 mL 1 DOSIS INYECTABLE")
        self.assertIsNone(attrs["mat"])
        self.assertIsNone(attrs["gauge"])


class ItemStyleTest(unittest.TestCase):
    def test_internal_name_style(self):
        self.assertEqual(
            fields(PGA_ITEM, "mat", "gauge", "curv", "type", "mm", "cm", "needles"),
            ("PGA", "0", "3/8", "CORTANTE", "35", "70", 1),
        )

    def test_surgical_wire_item_is_steel(self):
        self.assertEqual(
            fields("ALAMBRE QUIRÚRGICO 5 AGUJA 1/2 CÍRCULO CORTANTE 48 MM X 90 CM   MT", "mat", "curv", "type"),
            ("ACERO", "1/2", "CORTANTE"),
        )

    def test_item_without_aguja_word(self):
        text = "ÁCIDO POLIGLICÓLICO 2 1/2 CÍRCULO CORTANTE CONVENCIONAL 45 MM X 75 CM  VS"
        self.assertEqual(fields(text, "gauge", "curv", "type"), ("2", "1/2", "CORTANTE"))

    def test_item_sin_aguja_and_multiempaque(self):
        self.assertEqual(fields("CATGUT CRÓMICO 3/0 SIN AGUJA  X 70 CM DM", "mat", "gauge", "needles", "cm"),
                         ("CATGUT CROMICO", "3/0", 0, "70"))
        self.assertEqual(
            fields("SEDA NEGRA TRENZADA 2/0 MULTIEMPAQUE 10 HEBRAS X 75 CM  CON SOPORTE HE", "gauge", "needles"),
            ("2/0", 0),
        )

    def test_parse_item_strips_trailing_supplier_code(self):
        # "C/2A SD": the trailing code must not be read as needle type or gauge.
        text = "POLIGLACTIN 8/0 AGUJA 3/8 CÍRCULO ESPATULADA 6 MM X 75 CM C/2A  SD"
        attrs = parse_item(text)
        self.assertEqual((attrs["mat"], attrs["gauge"], attrs["needles"]), ("PGLA", "8/0", 2))


class ScoreTest(unittest.TestCase):
    def test_exact_match_across_catalog_styles(self):
        minsa = parse("SUTURA ACIDO POLIGLICOLICO 0 C/A 3/8 CIRCULO CORTANTE 35 mm x 70 cm   UNIDAD")
        item = parse_item(PGA_ITEM)
        self.assertTrue(core_exact(minsa, item))
        self.assertGreater(score(minsa, item), 0)

    def test_gauge_difference_breaks_exact_and_lowers_score(self):
        a = parse(SEDA_MINSA)
        same = parse_item("SEDA NEGRA TRENZADA 3/0 AGUJA 3/8 CÍRCULO CORTANTE 25 MM X 75 CM CP")
        other = parse_item("SEDA NEGRA TRENZADA 2/0 AGUJA 3/8 CÍRCULO CORTANTE 25 MM X 75 CM CP")
        self.assertTrue(core_exact(a, same))
        self.assertFalse(core_exact(a, other))
        self.assertGreater(score(a, same), score(a, other))

    def test_missing_attribute_is_not_exact(self):
        partial = parse("SUTURA SEDA NEGRA TRENZADA 3/0 C/A 3/8 TODO 25 mm")
        self.assertFalse(core_exact(partial, parse_item("SEDA NEGRA TRENZADA 3/0 AGUJA 3/8 CÍRCULO CORTANTE 25 MM X 75 CM CP")))

    def test_no_needle_suture_exact_on_material_gauge_and_length(self):
        minsa = parse("SUTURA SEDA NEGRA TRENZADA 0 S/A 45 cm   UNIDAD")
        item = parse_item("SEDA NEGRA TRENZADA 0 SIN AGUJA  X 45 CM CP")
        self.assertTrue(core_exact(minsa, item))
        needled = parse_item("SEDA NEGRA TRENZADA 0 AGUJA 3/8 CÍRCULO CORTANTE 25 MM X 45 CM CP")
        self.assertFalse(core_exact(minsa, needled))


if __name__ == "__main__":
    unittest.main()
