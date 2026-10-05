import json
import unittest
from pathlib import Path

from homologador.siga import candidatos, clave, elegir

MUESTRA = json.loads((Path(__file__).parent / "fixtures" / "siga_muestra.json").read_text(encoding="utf-8"))


def resolver(inicio):
    """Result for the fixture record whose MINSA name starts with ``inicio``."""
    registro = next(r for r in MUESTRA if r["nombre"].startswith(inicio))
    return elegir(registro["nombre"], candidatos(registro["raw1"], registro["raw2"]))


def codigos(resultado):
    return [o["codigo"] for o in resultado["opciones"]]


class CandidatosTest(unittest.TestCase):
    def test_union_dedupes_by_code_and_remembers_the_sources(self):
        raw1 = [["1", "UNO"], ["2", "DOS"]]
        raw2 = [{"v": "variante a", "rows": [["2", "DOS"], ["3", "TRES"]]}, {"v": "variante b", "rows": [["3", "TRES"]]}]
        r = {c["codigo"]: c for c in candidatos(raw1, raw2)}
        self.assertEqual(list(r), ["1", "2", "3"])
        self.assertEqual(r["1"]["fuentes"], ["pasada1"])
        self.assertEqual(r["2"]["fuentes"], ["pasada1", "variante a"])
        self.assertEqual(r["3"]["fuentes"], ["variante a", "variante b"])

    def test_empty_inputs_give_no_candidates(self):
        self.assertEqual(candidatos([], []), [])


class ClaveTest(unittest.TestCase):
    def test_normalization_ignores_accents_case_marks_and_trailing_unit(self):
        self.assertEqual(clave("GUANTE QUIRURGICO ESTERIL Nº 7 PUÑO LARGO (PAR)   UNIDAD"),
                         clave("Guante quirurgico esteril N° 7 puno largo"))
        self.assertEqual(clave('TUBO 1/4" X 3/8"'), clave("TUBO 1/4 in X 3/8 in"))
        self.assertNotEqual(clave("SUTURA NYLON 3/0"), clave("SUTURA NAILON 3/0"))


class SuturaTest(unittest.TestCase):
    def test_single_exact_description(self):
        r = resolver("SUTURA SEDA NEGRA TRENZADA 3/0 C/A 3/8 CIRCULO CORTANTE 30 mm X 75 cm")
        self.assertEqual((r["estado"], codigos(r), r["diferencias"], r["puntaje"]), ("exacto", ["495700580110"], "", 100))

    def test_exact_text_wins_over_other_core_equal_candidates(self):
        r = resolver("SUTURA DE POLIPROPILENO 6/0 C/A 3/8 CIRCULO CORTANTE 15 mm X 75 cm")
        self.assertEqual((r["estado"], codigos(r)[0]), ("exacto", "495701120215"))
        self.assertEqual(r["total"], 2)

    def test_exact_text_with_the_typo_mm_as_m(self):
        r = resolver("SUTURA ACIDO POLIGLACTIN 2/0 C/A 1/2 CIRCULO REDONDA 30 m X 75 cm")
        self.assertEqual((r["estado"], codigos(r)[0]), ("exacto", "495701350412"))

    def test_nylon_nailon_synonym_picks_the_same_calibre_and_lengths(self):
        r = resolver("SUTURA NYLON AZUL MONOFILAMENTO  0  C/A 1/2 CIRCULO REDONDA  20 mm x 75 cm")
        self.assertEqual((r["estado"], codigos(r)[0], r["diferencias"]), ("mejor_coincidencia", "495701360277", ""))
        # USP 1/0 is the same size as 0 but the notation 0 wins the tie; other calibres rank after.
        self.assertEqual(codigos(r)[1], "495701360316")

    def test_double_needle_c2a_matches_c_doble_aguja(self):
        r = resolver("SUTURA DE POLIESTER TRENZADO VERDE 3/0 C/2A 1/2 CIRCULO REDONDA 15 mm X 75 cm")
        self.assertEqual((r["estado"], codigos(r)[0], r["diferencias"]), ("mejor_coincidencia", "495700560623", ""))

    def test_equal_needle_length_beats_nearby_lengths(self):
        r = resolver("SUTURA SEDA VIRGEN 7/0 C/2A 3/8 CIRCULO ESPATULADA 7 mm X 45 cm")
        self.assertEqual((r["estado"], codigos(r)[0]), ("mejor_coincidencia", "495700580569"))

    def test_single_candidate_with_wording_differences(self):
        r = resolver("SUTURA SEDA NEGRA TRENZADA SILICONADA 6/0 C/2 A 1/4 CIRCULO CORTANTE ESPATULADA")
        self.assertEqual((r["estado"], codigos(r), r["total"]), ("mejor_coincidencia", ["495700580564"], 1))

    def test_single_needle_request_never_takes_the_four_needle_item_as_main(self):
        r = resolver("SUTURA DE ACERO INOXIDABLE MONOFILAMENTO 5 C/A 1/2 CIRCULO REDONDA 50 mm X 180 cm")
        self.assertEqual((r["estado"], codigos(r)[0]), ("exacto", "495700560641"))
        self.assertEqual(codigos(r)[1], "495700560633")

    def test_needle_abbreviations_in_the_minsa_name(self):
        r = resolver("SUTURA DE SEDA NEGRA TRENZADA NO 4/0 C/A  1/2 CR 20MM")
        self.assertEqual((r["estado"], codigos(r)[0]), ("mejor_coincidencia", "495700580235"))

    def test_unstated_thread_length_leaves_two_equal_candidates_ambiguous(self):
        r = resolver("SUTURA DE SEDA NEGRA TRENZADA NO 3/0 C/A  3/8 CC 30MM")
        self.assertEqual(r["estado"], "ambiguo")
        self.assertEqual(set(codigos(r)[:2]), {"495700580110", "495700580577"})

    def test_two_codes_with_the_same_description_are_ambiguous(self):
        r = resolver("SUTURA NAILON AZUL MONOFILAMENTO 3/0 C/A 3/8 CIRCULO CORTANTE 30 mm X 70 cm")
        self.assertEqual((r["estado"], sorted(codigos(r))), ("ambiguo", ["495701360496", "495701360536"]))

    def test_nearest_needle_length_is_chosen_when_none_is_equal(self):
        r = resolver("SUTURA ACIDO POLIGLACTIN 1/0 C/A 1/2 CIRCULO REDONDA 36 mm X 70 cm")
        self.assertEqual((r["estado"], codigos(r)[0], r["diferencias"]), ("mejor_coincidencia", "495701350512", "long_aguja:36!=36.4mm"))
        self.assertEqual(set(codigos(r)[1:3]), {"495701350631", "495701350506"})  # 37 mm and 35 mm are equally near
        self.assertTrue(all(o["puntaje"] < 100 for o in r["opciones"]))

    def test_other_calibres_only_are_approximate_with_the_nearest_size_first(self):
        r = resolver("SUTURA DE ACIDO POLIGLICOLICO Nº3 C/A 1/2 CIRCULO REDONDO 30 mmX 70 cm")
        self.assertEqual(r["estado"], "aproximado")
        self.assertEqual((codigos(r)[0], r["diferencias"]), ("495701350355", "calibre:3!=1"))
        self.assertLess(r["puntaje"], 80)

    def test_leading_2c_a_is_a_double_needle_and_c_2_agujas_is_the_same_product(self):
        r = resolver("SUTURA DE POLIPROPILENO 6/0 2C/A 3/8 CIRCULO REDONDA 13 mm x 75 cm")
        # C/DOBLE AGUJA and C/2 AGUJAS are the same product under two codes: tied, so ambiguous.
        self.assertEqual((r["estado"], set(codigos(r)[:2]), r["diferencias"]), ("ambiguo", {"495701120144", "495701120149"}, ""))
        self.assertNotIn("495701120065", codigos(r)[:2])  # the single-needle option never ranks with them

    def test_multipack_request_stays_among_multipacks_even_with_another_calibre(self):
        r = resolver("SUTURA SEDA NEGRA TRENZADA 2 S/A MULTIEMPAQUE 8 mm X 50 cm")
        self.assertEqual((r["estado"], codigos(r)[0], r["diferencias"]), ("aproximado", "495700580450", "calibre:2!=1"))

    def test_unstated_calibre_is_never_a_best_match(self):
        r = resolver("SUTURA CATGUT CROMICO   UNIDAD")
        self.assertEqual((r["estado"], r["total"] >= 8), ("aproximado", True))

    def test_reverse_cutting_request_without_that_wording_in_siga_is_approximate(self):
        r = resolver("SUTURA NYLON AZUL MONOFILAMENTO 5/0 C/A 1/2 PUNTA REVERSO CORTANTE 15 mm X 75 cm")
        self.assertEqual(r["estado"], "aproximado")
        self.assertEqual(codigos(r)[0], "495701360397")  # 1/2, same calibre and lengths: only the point differs
        self.assertEqual(r["diferencias"], "punta:reverso cortante!=cortante")

    def test_needle_less_request_against_an_undescribed_item_is_approximate(self):
        r = resolver("SUTURA LINO QUIRURGICO 2/0 S/A 8 mm X 70 cm")
        self.assertEqual((r["estado"], codigos(r)), ("aproximado", ["495700300045"]))
        self.assertIn("curvatura:sin aguja!=?", r["diferencias"])

    def test_no_candidates(self):
        for inicio in ("SUTURA DE ACIDO POLIGLACTIN (VICRYL", "SUTURA ABSORBIBLE CATGUT CROMICO 1/0"):
            r = resolver(inicio)
            self.assertEqual((r["estado"], r["opciones"], r["puntaje"], r["total"], r["diferencias"]), ("sin_resultado", [], 0, 0, ""))


class NoSuturaTest(unittest.TestCase):
    def test_exact_catheter(self):
        for inicio, esperado in [("CATETER VENOSO CENTRAL TRIPLE LUMEN 5.5 FR", "495701490051"),
                                 ("CATETER VENOSO CENTRAL 4 FR X 8 cm", "495700190746"),
                                 ("CATETER VENOSO CENTRAL DOBLE LUMEN 4 FR X 5", "495701490017")]:
            r = resolver(inicio)
            self.assertEqual((r["estado"], codigos(r)[0]), ("exacto", esperado), inicio)

    def test_exact_after_removing_parentheses_and_unit(self):
        r = resolver("GUANTE QUIRURGICO ESTERIL EMPAQUE INDIV. Nº 7 PUÑO LARGO")
        self.assertEqual((r["estado"], codigos(r)[0]), ("exacto", "495700290022"))

    def test_exact_blade(self):
        self.assertEqual(resolver("HOJA DE BISTURI DESCARTABLE Nº 12")["estado"], "exacto")

    def test_half_size_gloves_do_not_tie_with_the_whole_size(self):
        r = resolver("GUANTE QUIRURGICO ESTERIL EMPAQUE INDIV. Nº 7 1/2 PUÑO LARGO   PAR")
        self.assertEqual((r["estado"], codigos(r)[0]), ("mejor_coincidencia", "495700290021"))

    def test_other_material_gloves_are_only_approximate(self):
        r = resolver("GUANTE DE LATEX PARA EXAMEN NO ESTERIL TALLA M X 100 UNIDADES")
        self.assertEqual(r["estado"], "aproximado")
        self.assertLess(r["puntaje"], 90)

    def test_same_numbers_but_other_words_is_approximate_and_lists_the_words(self):
        r = resolver("AGUJA DE ANESTESIA ESPINAL DESCARTABLE Nº 22 G X 3 1/2")
        self.assertEqual((r["estado"], codigos(r)[0]), ("aproximado", "495700020090"))
        self.assertEqual(r["diferencias"], "palabras:ANESTESIA, ESPINAL!=LUMBAR, PUNCION")

    def test_same_size_gloves_with_and_without_powder_are_ambiguous(self):
        r = resolver("GUANTE PARA EXAMEN DE NITRILO TALLA S")
        self.assertEqual((r["estado"], set(codigos(r)[:2])), ("ambiguo", {"495700280136", "495700280143"}))
        self.assertNotIn(codigos(r)[0], ("495700280156",))  # XS is a different size


if __name__ == "__main__":
    unittest.main()
