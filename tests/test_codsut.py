import json
import unittest
from pathlib import Path

from homologador.codsut import atributos_item, atributos_texto, parse_codsut

ESTRUCTURA = Path(__file__).resolve().parent.parent / "items" / "codsut_estructura.json"
DICTIONARIES = ("marca", "hebra", "calibre", "aguja", "long_aguja", "long_hebra", "caja", "clase", "campo_variable")


class EstructuraJsonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(ESTRUCTURA.read_text(encoding="utf-8"))

    def test_nine_dictionaries_of_code_to_description(self):
        self.assertEqual(list(self.data), list(DICTIONARIES))
        for name, entries in self.data.items():
            self.assertTrue(entries, name)
            self.assertTrue(all(isinstance(k, str) and isinstance(v, str) for k, v in entries.items()), name)

    def test_codes_have_the_positional_widths(self):
        widths = dict(zip(DICTIONARIES, (2, 2, 3, 2, 3, 3, 2, 1, 3)))
        for name, width in widths.items():
            self.assertEqual({len(code) for code in self.data[name]}, {width}, name)

    def test_known_entries_of_the_example_code(self):
        # CPAP010TC35007024ASCE = CP / AP / 010 / TC / 350 / 070 / 24 / A / SCE
        self.assertEqual(self.data["marca"]["CQ"], "CIRUGIA PERUANA PLUS")
        self.assertEqual(self.data["hebra"]["AP"], "ACIDO POLIGLICOLICO")
        self.assertEqual(self.data["calibre"]["020"], "2/0")
        self.assertEqual(self.data["calibre"]["010"], "0")
        self.assertEqual(self.data["calibre"]["001"], "1")
        self.assertEqual(self.data["long_aguja"]["350"], "35 mm")
        self.assertEqual(self.data["long_hebra"]["070"], "70 cm")
        self.assertEqual(self.data["caja"]["24"], "24 unid.")
        self.assertEqual(self.data["clase"]["B"], "Estéril Doble Aguja")


class ParseCodsutTest(unittest.TestCase):
    def test_example_code_from_the_dictionary(self):
        a = parse_codsut("CPAP010TC35007024ASCE")
        self.assertEqual((a["marca"], a["hebra"], a["familia"], a["variante"]), ("CP", "AP", "PGA", frozenset()))
        self.assertEqual((a["calibre"], a["curvatura"], a["punta"]), ("0", "3/8", "cortante"))
        self.assertEqual((a["long_aguja"], a["long_hebra"], a["caja"], a["clase"], a["doble"]), (35.0, 70.0, "24", "A", False))

    def test_silk_black_braided(self):
        a = parse_codsut("SDST020MC40007536ASCE")
        self.assertEqual((a["familia"], a["variante"], a["calibre"]), ("SEDA", frozenset({"negro", "trenzado"}), "2/0"))
        self.assertEqual((a["curvatura"], a["punta"], a["long_aguja"], a["long_hebra"]), ("1/2", "cortante", 40.0, 75.0))

    def test_nylon_kinds_stay_distinct(self):
        blue = parse_codsut("SDNM030RC60008036ASCE")
        black = parse_codsut("SDNN040TC12007536ASCE")
        self.assertEqual((blue["familia"], blue["variante"]), ("NYLON", frozenset({"azul", "monofilamento"})))
        self.assertEqual(black["variante"], frozenset({"negro", "monofilamento"}))
        self.assertEqual((blue["curvatura"], blue["punta"]), ("recta", "cortante"))
        self.assertEqual(parse_codsut("SDNT030XM08M07024ASCE")["variante"], frozenset({"negro", "trenzado"}))

    def test_hebra_families_and_variants(self):
        for hebra, familia, variante in [
            ("AA", "PGA", {"antibacterial"}), ("AI", "PGA", {"incoloro"}), ("CC", "CATGUT CROMICO", set()),
            ("CS", "CATGUT SIMPLE", set()), ("PD", "PDO", set()), ("PB", "PDO", {"antibacterial"}),
            ("DB", "PDO", {"barbed"}), ("BY", "PDO", {"violeta", "barbed"}), ("PW", "POLIESTER", {"blanco"}),
            ("UB", "POLIETILENO", {"negro"}), ("AG", "PGLA", set()), ("PX", "PGLA", {"antibacterial", "incoloro"}),
            ("PQ", "PGLA", {"quick"}), ("PT", "PGC", {"antibacterial"}), ("BZ", "PGC", {"violeta", "barbed"}),
            ("PP", "POLIPROPILENO", set()), ("FR", "POLIPROPILENO", {"fluorescente", "rosado"}),
            ("PO", "POLIPROPILENO", {"incoloro"}), ("BT", "SEDA", {"blanco", "trenzado"}), ("AQ", "ACERO", set()),
            ("HM", "ACERO", {"marcapaso"}), ("LI", "LINO", set()),
        ]:
            a = parse_codsut(f"SD{hebra}030MC40007536ASCE")
            self.assertEqual((a["familia"], a["variante"]), (familia, frozenset(variante)), hebra)

    def test_no_needle_spool_and_multipack(self):
        a = parse_codsut("SDAP030SA00C15036ASCE")  # AP 3/0 SIN AGUJA X 150 CM
        self.assertEqual((a["curvatura"], a["punta"], a["long_aguja"], a["long_hebra"]), ("sin aguja", None, None, 150.0))
        a = parse_codsut("CQLI030XM10M07524ASCE")  # LINO 3/0 MULTIEMPAQUE 10 HEBRAS X 75 CM
        self.assertEqual((a["curvatura"], a["hebras"], a["long_aguja"], a["long_hebra"]), ("multiempaque", 10, None, 75.0))
        a = parse_codsut("CQNN001CA00C91000NSCE")  # NYLON NEGRO MONOFILAMENTO 1 CARRETE X 100 YD
        self.assertEqual((a["curvatura"], a["calibre"], a["long_hebra"], a["clase"]), ("carrete", "1", 9144.0, "N"))

    def test_double_needle_class(self):
        a = parse_codsut("SDAG060QE07604512BSCE")  # POLIGLACTIN 6/0 1/4 ESPATULADA 7.6 MM X 45 CM C/2A
        self.assertEqual((a["clase"], a["doble"], a["curvatura"], a["punta"], a["long_aguja"]), ("B", True, "1/4", "espatulada", 7.6))

    def test_needle_points_from_the_description(self):
        for aguja, curvatura, punta in [
            ("EC", "1/8", "reverso cortante"), ("MR", "1/2", "redonda"), ("MQ", "1/2", "cortante"),
            ("TG", "3/8", "cortante"), ("TL", "3/8", "micropunta"), ("QV", "1/4", "tapercut"),
            ("MF", "1/2", "taper"), ("TB", "3/8", "roma"), ("OH", "curva compuesta", "reverso cortante"),
            ("RC", "recta", "cortante"), ("RG", "recta", None), ("JT", "jota", None), ("UR", "5/8", "redonda"),
            ("MS", "1/2", "espatulada"), ("TT", "3/8", "redonda"),
        ]:
            a = parse_codsut(f"SDAP030{aguja}40007536ASCE")
            self.assertEqual((a["curvatura"], a["punta"]), (curvatura, punta), aguja)

    def test_unknown_or_blank_codes_give_none_never_raise(self):
        a = parse_codsut("SDFC020MR40007012ASCE")  # FC (collagen) is not in the hebra dictionary
        self.assertIsNone(a["familia"])
        self.assertEqual((a["calibre"], a["curvatura"], a["long_aguja"]), ("2/0", "1/2", 40.0))
        for blank in ("", None, "          ", "SDSUTCJ12SCV", "XX"):
            a = parse_codsut(blank)
            self.assertIsNone(a["familia"])
            self.assertIsNone(a["calibre"])
        self.assertEqual(parse_codsut("SDPP080TS08007512B")["clase"], "B")  # 18 chars, truncated tail


class AtributosItemTest(unittest.TestCase):
    def test_text_fills_what_the_code_does_not_know(self):
        a = atributos_item(
            "SDPM005MR45010012ASCE",
            "POLIETILENO ULTRA ALTO PESO MOLECULAR BLANCO VERDE 5 AGUJA 1/2 CÍRCULO REDONDA 45 MM X 100 CM  SD",
        )
        self.assertEqual((a["familia"], a["calibre"], a["curvatura"], a["punta"]), ("POLIETILENO", "5", "1/2", "redonda"))

    def test_code_wins_over_text(self):
        a = atributos_item("SDST020MC40007536ASCE", "SEDA NEGRA TRENZADA 2/0 AGUJA 3/8 CÍRCULO REDONDA 40 MM X 75 CM SD")
        self.assertEqual((a["curvatura"], a["punta"]), ("1/2", "cortante"))

    def test_blank_code_uses_text_only(self):
        a = atributos_item("", "ÁCIDO POLIGLICÓLICO 3/0 AGUJA 3/8 CÍRCULO CORTANTE 30 MM X 75 CM SD")
        self.assertEqual((a["familia"], a["calibre"], a["curvatura"], a["punta"], a["long_aguja"], a["long_hebra"]),
                         ("PGA", "3/0", "3/8", "cortante", 30.0, 75.0))


class AtributosTextoTest(unittest.TestCase):
    def campos(self, nombre, *keys):
        a = atributos_texto(nombre)
        return tuple(a[k] for k in keys)

    def test_needle_abbreviations_with_needle_length(self):
        for nombre, esperado in [
            ("SUTURA DE SEDA NEGRA TRENZADA NO 3/0 C/A  3/8 CC 30MM UNIDAD", ("3/8", "cortante", 30.0)),
            ("SUTURA NYLON AZUL MONOFILAMENTO NO 3/0 C/A  1/2 CR 30MM UNIDAD", ("1/2", "redonda", 30.0)),
            ("SUTURA NYLON AZUL MONOFILAMENTO NO 2/0 C/A  1/2CR 40MM UNIDAD", ("1/2", "redonda", 40.0)),
            ("SUTURA NYLON AZUL MONOFILAMENTO 75 CM  4/0 3/8 CT UNIDAD", ("3/8", "cortante", None)),
            ("SUTURA NYLON AZUL MONOFILAMENTO  1 1/2 CC 25 UNIDAD", ("1/2", "cortante", 25.0)),
        ]:
            self.assertEqual(self.campos(nombre, "curvatura", "punta", "long_aguja"), esperado, nombre)

    def test_needle_codes_of_the_dictionary_with_length(self):
        for nombre, esperado in [
            ("SUTURA POLIPROPILENO 4/0 MR 20   UNIDAD", ("1/2", "redonda", 20.0)),
            ("SUTURA CATGUT CROMICO 2 C/A MR-35  UNIDAD", ("1/2", "redonda", 35.0)),
            ("SUTURA NYLON AZUL MONOFILAMENTO 6/0 C/A 1/2 MC 20   UNIDAD", ("1/2", "cortante", 20.0)),
            ("SUTURA SEDA NEGRA TRENZADA 3/0 C/A CC 30 (TC 30)   UNIDAD", ("3/8", "cortante", 30.0)),
        ]:
            self.assertEqual(self.campos(nombre, "curvatura", "punta", "long_aguja"), esperado, nombre)

    def test_usp_one_zero_is_calibre_zero(self):
        self.assertEqual(self.campos("SUTURA CATGUT CROMICO 1/0 C/A 1/2 CIRCULO CORTANTE 35 mm X 70 cm   UNIDAD", "calibre"), ("0",))
        self.assertEqual(self.campos("SUTURA SEDA NEGRA TRENZADA 2/0 C/A 1/2 CIRCULO CORTANTE 35 mm X 70 cm", "calibre"), ("2/0",))

    def test_multipack_ignores_the_stray_millimetres(self):
        a = atributos_texto("SUTURA SEDA NEGRA TRENZADA MULTIEMPAQUE 3/0 S/A 8 mm X 50 cm   UNIDAD")
        self.assertEqual((a["curvatura"], a["long_aguja"], a["long_hebra"]), ("multiempaque", None, 50.0))

    def test_synonyms_and_variants(self):
        self.assertEqual(self.campos("SUTURA DEXON 3/0 C/A 1/2 CIRCULO REDONDA 26 mm X 70 cm", "familia"), ("PGLA",))
        self.assertEqual(self.campos("SUTURA NAILON NEGRO MONOFILAMENTO 8/0 C/DOBLE AGUJA 3/8 CIRCULO REDONDA 6.5 mm X 30 cm", "familia", "variante", "doble"),
                         ("NYLON", frozenset({"negro", "monofilamento"}), True))
        self.assertEqual(self.campos("SUTURA ACIDO POLIGLACTIN 7/0 C/A ESPATULA 3/8 CIRCULAR X 6.5 mm X 45 cm", "curvatura", "punta", "long_aguja"),
                         ("3/8", "espatulada", 6.5))

    def test_siga_wording_inverted_cut_is_reverse_cutting(self):
        self.assertEqual(self.campos("SUTURA SEDA NEGRA TRENZADA 4/0 C/A 3/8 CORTE INVERTIDO 20 mm X 75 cm", "curvatura", "punta"), ("3/8", "reverso cortante"))

    def test_barbed_suture_has_no_family_but_keeps_its_attributes(self):
        a = atributos_texto("SUTURA CON PUAS UNIDIRECCIONAL MONOFILAMENTO VIOLETA 3/0 C/A 1/2 CIRCULO PUNTA CILINDRICA 26 mm X 30 cm   UNIDAD")
        self.assertEqual((a["familia"], a["calibre"], a["curvatura"], a["punta"], a["long_aguja"], a["long_hebra"]),
                         (None, "3/0", "1/2", "cilindrica", 26.0, 30.0))
        self.assertEqual(a["variante"], frozenset({"barbed", "violeta", "monofilamento"}))


if __name__ == "__main__":
    unittest.main()
