import json
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
