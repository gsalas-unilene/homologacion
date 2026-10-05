import csv
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import lancedb
import pyarrow as pa

import homologar
import mcp_server

GENERATION = "c" * 32
METADATA = {
    "embedding_model": "test-model",
    "embedding_profile": "homologacion-text-v1",
    "embedding_dimension": 2,
    "embedding_schema_version": 1,
}
META_FIELDS = [
    pa.field("embedding_model", pa.string()),
    pa.field("embedding_profile", pa.string()),
    pa.field("embedding_dimension", pa.int32()),
    pa.field("embedding_schema_version", pa.int32()),
]
SEDA = "SUTURA SEDA NEGRA TRENZADA 3/0 C/A 3/8 CIRCULO CORTANTE 25 mm X 75 cm   UNIDAD"
CATETER = "CATETER VENOSO CENTRAL 4 FR X 13 cm   UNIDAD"
VACUNA = "VACUNA CONTRA LA HEPATITIS A 720 UI/0.5 mL 1 DOSIS INYECTABLE"
ITEMS = [
    ("S1", "SEDA NEGRA TRENZADA 3/0 AGUJA 3/8 CÍRCULO CORTANTE 25 MM X 75 CM CP", "01. SUTURAS", [1.0, 0.0]),
    ("C1", "CATETER VENOSO CENTRAL SIMPLE LUMEN 4 FR X 13 CM. X UN. CP", "13. OTROS", [0.1, 0.995]),
    # Decoy: closer to the catheter row than C1, but a suture item; non-suture rows must not see it.
    ("D1", "CATETER VENOSO CENTRAL 4 FR X 13 CM", "01. SUTURAS", [0.0, 1.0]),
]
MINSA = [("00001", SEDA, [1.0, 0.0]), ("00002", CATETER, [0.0, 1.0]), ("00003", VACUNA, [0.7071, 0.7071]),
         ("00004", "TORNILLO PARA HUESO 4.0 mm", [0.6, 0.8])]


def create_catalog(path):
    path.mkdir()
    (path / "active_catalogs.json").write_text(
        json.dumps({"generation": GENERATION, "items_table": f"catalogo_items__{GENERATION}",
                    "minsa_table": f"catalogo_minsa__{GENERATION}", **METADATA}),
        encoding="utf-8",
    )
    vector = pa.field("vector", pa.list_(pa.float32()))
    text = pa.string()
    item_schema = pa.schema([pa.field(n, text) for n in ("row_id", "Coditem", "Item", "CodSubFamilia", "SubFamilia",
                                                          "CodAgrupador", "Agrupador")] + META_FIELDS + [vector])
    minsa_schema = pa.schema([pa.field(n, text) for n in ("row_id", "CodigoMed", "NombreMed")] + META_FIELDS + [vector])
    database = lancedb.connect(str(path))
    database.create_table(
        f"catalogo_items__{GENERATION}",
        data=pa.Table.from_pylist(
            [{"row_id": c, "Coditem": c, "Item": i, "CodSubFamilia": "", "SubFamilia": "", "CodAgrupador": "",
              "Agrupador": a, **METADATA, "vector": v} for c, i, a, v in ITEMS], schema=item_schema),
    )
    database.create_table(
        f"catalogo_minsa__{GENERATION}",
        data=pa.Table.from_pylist(
            [{"row_id": f"minsa:{c}", "CodigoMed": c, "NombreMed": n, **METADATA, "vector": v} for c, n, v in MINSA],
            schema=minsa_schema),
    )


class HomologarTest(unittest.TestCase):
    def run_catalog(self, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_catalog(root / "db")
            salida = root / "salida" / "homologacion.csv"
            items_csv = root / "items.csv"
            with items_csv.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, ["Coditem", "CodSut", "Item", "Agrupador"])
                writer.writeheader()
                writer.writerow({"Coditem": "PSTSN02412", "CodSut": "SDST030TC25007512ASCE", "Agrupador": "01. SUTURAS",
                                 "Item": "SEDA NEGRA TRENZADA 3/0 AGUJA 3/8 CÍRCULO CORTANTE 25 MM X 75 CM SD"})
            with patch.object(mcp_server, "DB_PATH", root / "db"):
                counts = homologar.homologar(salida, items_csv=items_csv, **kwargs)
            raw = salida.read_bytes()
            with salida.open(encoding="utf-8-sig", newline="") as stream:
                return counts, raw, list(csv.DictReader(stream))

    def test_writes_bom_csv_with_a_row_and_tier_per_minsa_row(self):
        counts, raw, rows = self.run_catalog()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(list(rows[0]), ["CodigoMed", "NombreMed", "Coditem", "Item", "Agrupador", "tier",
                                         "distance", "score", "alt_2", "alt_3", "marca", "CodSut", "diferencias"])
        by_code = {r["CodigoMed"]: r for r in rows}
        self.assertEqual({k: (v["tier"], v["Coditem"]) for k, v in by_code.items()},
                         {"00001": ("exacto", "PSTSN02412"), "00002": ("revisar", "C1"),
                          "00003": ("sin_equivalente", ""), "00004": ("sin_equivalente", "")})
        self.assertEqual(counts, Counter(exacto=1, revisar=1, sin_equivalente=2))

    def test_suture_rows_get_brand_and_codsut_and_generic_rows_leave_them_empty(self):
        _, _, rows = self.run_catalog()
        by_code = {r["CodigoMed"]: r for r in rows}
        self.assertEqual((by_code["00001"]["marca"], by_code["00001"]["CodSut"], by_code["00001"]["distance"]),
                         ("SD", "SDST030TC25007512ASCE", ""))
        self.assertEqual((by_code["00002"]["marca"], by_code["00002"]["CodSut"], by_code["00002"]["diferencias"]), ("", "", ""))

    def test_limit_processes_only_the_first_rows(self):
        counts, _, rows = self.run_catalog(limit=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(counts.values()), 2)

    def test_small_batches_cover_every_row_once(self):
        with patch.object(homologar, "BATCH", 3):
            _, _, rows = self.run_catalog()
        self.assertEqual(sorted(r["CodigoMed"] for r in rows), ["00001", "00002", "00003", "00004"])


if __name__ == "__main__":
    unittest.main()
