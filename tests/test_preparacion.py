import csv
import gc
import ast
import io
import json
import math
import os
import sys
import tempfile
import unittest
import weakref
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import poblar_catalogo as preparation


MODEL = preparation.FASTEMBED_DEFAULT_MODEL
JINA_MODEL = "jinaai/jina-embeddings-v2-base-es"


class FakeEmbedder:
    """Stands in for fastembed.TextEmbedding; never loads or downloads a model."""

    def __init__(self, vector_factory=None, dimension=384):
        self.calls = []
        self.vector_factory = vector_factory
        self.dimension = dimension

    def embed(self, texts):
        call_number = len(self.calls)
        self.calls.append(list(texts))
        if self.vector_factory:
            return iter(self.vector_factory(texts, call_number))
        return iter(
            [float(index + 1)] + [0.5] * (self.dimension - 1) for index in range(len(texts))
        )


def embedder_patches(embedder):
    return patch.object(preparation, "_load_embedder", return_value=embedder)


class FakeArrowTable:
    active = weakref.WeakSet()
    sizes = []
    peak_active = 0

    def __init__(self, rows, schema):
        self.rows = rows
        self.schema = schema

    @classmethod
    def reset(cls):
        gc.collect()
        cls.active = weakref.WeakSet()
        cls.sizes = []
        cls.peak_active = 0

    @classmethod
    def from_pylist(cls, rows, schema):
        gc.collect()
        table = cls(rows, schema)
        cls.active.add(table)
        cls.sizes.append(len(rows))
        cls.peak_active = max(cls.peak_active, len(cls.active))
        return table


class FakeLanceTable:
    def __init__(self, database, name):
        self.database = database
        self.name = name

    def add(self, data):
        self.database._record(self.name, "add")
        self.database.tables[self.name]["count"] += len(data.rows)
        if self.database.retain_data:
            self.database.tables[self.name]["rows"].extend(data.rows)


class FakeDatabase:
    def __init__(self, fail_at=None, retain_data=False):
        self.calls = []
        self.tables = {}
        self.fail_at = fail_at
        self.retain_data = retain_data

    def _record(self, name, operation):
        self.calls.append((name, operation))
        if len(self.calls) == self.fail_at:
            raise RuntimeError("table write failed")

    def create_table(self, name, data, mode):
        self._record(name, mode)
        self.tables[name] = {"count": len(data.rows), "rows": list(data.rows) if self.retain_data else []}
        return FakeLanceTable(self, name)


def items_csv(rows):
    header = "Coditem,Item,CodSubFamilia,SubFamilia,CodAgrupador,Agrupador\n"
    return header + "".join(",".join(row) + "\n" for row in rows)


def item_row(index):
    code = f"{index:05d}"
    return {
        "row_id": code,
        "Coditem": code,
        "Item": f"Item {index}",
        "CodSubFamilia": "0007",
        "SubFamilia": "Familia",
        "CodAgrupador": "01",
        "Agrupador": "Agrupador",
    }


def publication_rows():
    metadata = {
        "embedding_model": MODEL,
        "embedding_profile": preparation.EMBEDDING_PROFILE,
        "embedding_dimension": 2,
        "embedding_schema_version": 1,
        "vector": [1.0, 0.5],
    }
    return (
        [{**item_row(1), **metadata}],
        [{"row_id": "minsa:row", "CodigoMed": "06385", "NombreMed": "Medicine", **metadata}],
    )


def fake_database_modules(database):
    lancedb = ModuleType("lancedb")
    lancedb.connect = lambda _path: database

    pyarrow = ModuleType("pyarrow")
    pyarrow.field = lambda name, value_type: (name, value_type)
    pyarrow.string = lambda: "string"
    pyarrow.int32 = lambda: "int32"
    pyarrow.float32 = lambda: "float32"
    pyarrow.list_ = lambda value_type: ("list", value_type)
    pyarrow.schema = lambda fields: tuple(fields)
    pyarrow.Table = FakeArrowTable
    return {"lancedb": lancedb, "pyarrow": pyarrow}


class PreparationTests(unittest.TestCase):
    def setUp(self):
        fixture_dir = tempfile.TemporaryDirectory()
        self.addCleanup(fixture_dir.cleanup)
        self.config_fixture = Path(fixture_dir.name) / "config.fixture"
        self.config_fixture.write_text(
            f"FASTEMBED_MODEL='{JINA_MODEL}'\n",
            encoding="utf-8",
        )
        config_path = patch.object(preparation, "DOTENV_PATH", self.config_fixture)
        config_path.start()
        self.addCleanup(config_path.stop)

    def test_model_defaults_when_unset_and_env_wins_over_dotenv_fixture(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(preparation._load_fastembed_model(), JINA_MODEL)
            self.config_fixture.write_text("OTHER=1\n", encoding="utf-8")
            self.assertEqual(preparation._load_fastembed_model(), MODEL)
        self.config_fixture.write_text('FASTEMBED_MODEL="DO_NOT_USE_FILE_MODEL"\n', encoding="utf-8")
        with patch.dict(os.environ, {"FASTEMBED_MODEL": JINA_MODEL}, clear=True):
            self.assertEqual(preparation._load_fastembed_model(), JINA_MODEL)

    def test_dotenv_config_is_loaded_at_call_time_for_the_run(self):
        items = [item_row(1)]
        minsa = [{"row_id": "minsa:id", "CodigoMed": "06385", "NombreMed": "Medicine"}]
        embedder = FakeEmbedder(dimension=768)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(preparation, "_load_items", return_value=items),
            patch.object(preparation, "_load_minsa", return_value=minsa),
            patch.object(preparation, "_load_embedder", return_value=embedder) as load,
            patch.object(preparation, "_publish_tables"),
        ):
            preparation.poblar_catalogo()
        load.assert_called_once_with(JINA_MODEL)

    def test_rejected_model_names_allowed_models_without_leaking_the_value(self):
        items = [item_row(1)]
        minsa = [{"row_id": "minsa:id", "CodigoMed": "06385", "NombreMed": "Medicine"}]
        for source in ("env", "dotenv"):
            with self.subTest(source=source):
                environment = {}
                if source == "env":
                    environment = {"FASTEMBED_MODEL": "DO_NOT_LEAK_MODEL"}
                else:
                    self.config_fixture.write_text('FASTEMBED_MODEL="DO_NOT_LEAK_MODEL"\n', encoding="utf-8")
                with (
                    patch.dict(os.environ, environment, clear=True),
                    patch.object(preparation, "_load_items", return_value=items),
                    patch.object(preparation, "_load_minsa", return_value=minsa),
                    patch.object(preparation, "_load_embedder") as load,
                    patch.object(preparation, "_publish_tables") as publish,
                ):
                    with self.assertRaisesRegex(ValueError, "FASTEMBED_MODEL must be one of") as error:
                        preparation.poblar_catalogo()
                message = str(error.exception)
                self.assertNotIn("DO_NOT_LEAK_MODEL", message)
                for allowed in preparation.FASTEMBED_ALLOWED_MODELS:
                    self.assertIn(allowed, message)
                load.assert_not_called()
                publish.assert_not_called()

    def test_embedder_is_built_lazily_with_cache_dir_and_threads(self):
        fastembed = ModuleType("fastembed")
        fastembed.TextEmbedding = MagicMock(name="TextEmbedding")
        with patch.dict(sys.modules, {"fastembed": fastembed}):
            result = preparation._load_embedder(MODEL)
        fastembed.TextEmbedding.assert_called_once_with(
            MODEL,
            cache_dir=str(preparation.FASTEMBED_CACHE_DIR),
            threads=preparation.EMBEDDING_THREADS,
        )
        self.assertIs(result, fastembed.TextEmbedding.return_value)
        self.assertEqual(preparation.FASTEMBED_CACHE_DIR.name, ".fastembed_cache")

    def test_mcp_server_stays_embedder_free(self):
        source = (Path(preparation.__file__).parent / "mcp_server.py").read_text(encoding="utf-8")
        banned = ("fastembed", "urllib", "http", "httpx", "requests", "aiohttp", "onnxruntime")
        imported = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        offenders = [name for name in imported if name.split(".")[0] in banned]
        self.assertEqual(offenders, [])

    def test_csv_validation_preserves_codes_and_minsa_row_identity(self):
        items = preparation._items_from_csv(
            io.StringIO(items_csv([["00123", "Item", "0007", "Familia", "01", "Grupo"]]))
        )
        source = (
            "CodigoMed,NombreMed\n06385,Medicamento A\n06385,Medicamento B\n"
            "06385,Medicamento A\n"
        )
        minsa = preparation._minsa_from_csv(io.StringIO(source))
        repeated = preparation._minsa_from_csv(io.StringIO(source))

        self.assertEqual(items[0]["Coditem"], "00123")
        self.assertEqual(items[0]["CodSubFamilia"], "0007")
        self.assertEqual([row["CodigoMed"] for row in minsa], ["06385"] * 3)
        self.assertEqual(len({row["row_id"] for row in minsa}), 3)
        self.assertEqual([row["row_id"] for row in minsa], [row["row_id"] for row in repeated])

        with self.assertRaisesRegex(ValueError, "missing CSV columns"):
            preparation._items_from_csv(io.StringIO("Coditem,Item\n1,Item\n"))
        with self.assertRaisesRegex(ValueError, "duplicate Coditem"):
            preparation._items_from_csv(
                io.StringIO(items_csv([
                    ["00123", "Item A", "1", "Family", "1", "Group"],
                    ["00123", "Item B", "1", "Family", "1", "Group"],
                ]))
            )

    def test_minsa_missing_name_is_logged_excluded_and_never_embedded(self):
        items = [item_row(1)]
        minsa_csv = "CodigoMed,NombreMed\n06385,Medicine A\n99917,\n55276,Medicine B\n"
        embedder = FakeEmbedder()
        published = {}

        def load_minsa(_path):
            return preparation._minsa_from_csv(io.StringIO(minsa_csv))

        def capture_publication(_path, item_batches, minsa_batches, item_count, minsa_count):
            published.update(
                item_rows=[row for batch in item_batches for row in batch],
                minsa_rows=[row for batch in minsa_batches for row in batch],
                item_count=item_count,
                minsa_count=minsa_count,
            )

        with (
            patch.dict(os.environ, {"FASTEMBED_MODEL": MODEL}),
            patch.object(preparation, "_load_items", return_value=items),
            patch.object(preparation, "_load_minsa", side_effect=load_minsa),
            embedder_patches(embedder),
            patch.object(preparation, "_publish_tables", side_effect=capture_publication),
            self.assertLogs(level="WARNING") as logs,
        ):
            preparation.poblar_catalogo()

        self.assertTrue(any("99917" in message and "NombreMed is empty" in message for message in logs.output))
        self.assertEqual([len(batch) for batch in embedder.calls], [1, 2])
        self.assertEqual(embedder.calls[1], ["Medicine A", "Medicine B"])
        self.assertEqual(len(published["minsa_rows"]), 2)
        self.assertEqual(published["minsa_count"], 2)
        self.assertEqual([row["CodigoMed"] for row in published["minsa_rows"]], ["06385", "55276"])

    def test_minsa_still_rejects_empty_codes_and_all_rows_without_names(self):
        with self.assertRaisesRegex(ValueError, "empty CodigoMed"):
            preparation._minsa_from_csv(io.StringIO("CodigoMed,NombreMed\n,Medicine\n"))

        with self.assertLogs(level="WARNING") as logs:
            with self.assertRaisesRegex(ValueError, "no usable rows"):
                preparation._minsa_from_csv(
                    io.StringIO("CodigoMed,NombreMed\n11111,\n22222,\n")
                )
        self.assertEqual(len(logs.output), 2)

    def test_csv_reader_rejects_unterminated_quotes(self):
        malformed = (
            "Coditem,Item,CodSubFamilia,SubFamilia,CodAgrupador,Agrupador\n"
            '00123,"unfinished,0007,Family,01,Group\n'
        )
        with self.assertRaises(csv.Error):
            preparation._items_from_csv(io.StringIO(malformed))

    def test_publishes_both_tables_with_bounded_batches_and_compatibility_fields(self):
        items = [item_row(index) for index in range(65)]
        minsa = preparation._minsa_from_csv(
            io.StringIO("CodigoMed,NombreMed\n06385,Medicamento A\n06385,Medicamento B\n")
        )
        embedder = FakeEmbedder()
        published = {}

        def capture_publication(db_path, item_batches, minsa_batches, item_count, minsa_count):
            published.update(
                db_path=db_path,
                item_rows=[row for batch in item_batches for row in batch],
                minsa_rows=[row for batch in minsa_batches for row in batch],
                item_count=item_count,
                minsa_count=minsa_count,
            )

        with (
            patch.dict(os.environ, {"FASTEMBED_MODEL": MODEL}),
            patch.object(preparation, "_load_items", return_value=items),
            patch.object(preparation, "_load_minsa", return_value=minsa),
            patch.object(preparation, "_load_embedder", return_value=embedder) as load,
            patch.object(preparation, "_publish_tables", side_effect=capture_publication) as publish,
        ):
            preparation.poblar_catalogo()

        self.assertEqual([len(batch) for batch in embedder.calls], [64, 1, 2])
        load.assert_called_once_with(MODEL)
        publish.assert_called_once()
        self.assertEqual(published["db_path"], preparation.DB_PATH)
        self.assertEqual((published["item_count"], published["minsa_count"]), (65, 2))
        self.assertEqual(
            (preparation.ITEMS_TABLE, preparation.MINSA_TABLE),
            ("catalogo_items", "catalogo_minsa"),
        )
        item_rows, minsa_rows = published["item_rows"], published["minsa_rows"]
        self.assertEqual(item_rows[0]["Coditem"], "00000")
        self.assertEqual(item_rows[0]["row_id"], "00000")
        self.assertEqual(item_rows[64]["Coditem"], "00064")
        self.assertEqual(item_rows[64]["Item"], "Item 64")
        self.assertEqual(minsa_rows[0]["CodigoMed"], "06385")
        self.assertNotEqual(minsa_rows[0]["row_id"], minsa_rows[1]["row_id"])
        for row in (item_rows[0], minsa_rows[0]):
            self.assertEqual(row["embedding_model"], MODEL)
            self.assertEqual(row["embedding_profile"], preparation.EMBEDDING_PROFILE)
            self.assertEqual(row["embedding_dimension"], 384)
            self.assertEqual(row["embedding_schema_version"], 1)
            self.assertEqual(len(row["vector"]), 384)
            self.assertAlmostEqual(math.hypot(*row["vector"]), 1.0)

    def test_vectors_are_unit_normalized_and_numpy_output_becomes_plain_floats(self):
        import numpy

        embedder = FakeEmbedder(
            lambda texts, _call: [numpy.array([3.0, 4.0], dtype=numpy.float32) for _ in texts]
        )
        vectors = preparation._embed(["a", "b"], embedder)
        for vector in vectors:
            self.assertIs(type(vector), list)
            self.assertTrue(all(type(value) is float for value in vector))
            self.assertAlmostEqual(vector[0], 0.6, places=6)
            self.assertAlmostEqual(vector[1], 0.8, places=6)
            self.assertAlmostEqual(math.hypot(*vector), 1.0)

    def test_zero_norm_vector_is_rejected(self):
        embedder = FakeEmbedder(lambda texts, _call: [[1.0, 0.0], [0.0, 0.0]][: len(texts)])
        with self.assertRaisesRegex(ValueError, "zero-norm"):
            preparation._embed(["a", "b"], embedder)

    def test_dimension_comes_from_model_output(self):
        embedder = FakeEmbedder(dimension=768)
        rows = next(preparation._embedded_row_batches([item_row(1)], JINA_MODEL, embedder, lambda r: r["Item"]))
        self.assertEqual(rows[0]["embedding_dimension"], 768)
        self.assertEqual(len(rows[0]["vector"]), 768)
        self.assertEqual(rows[0]["embedding_model"], JINA_MODEL)

    def test_embed_rejects_batches_outside_the_configured_limit(self):
        embedder = FakeEmbedder()
        for texts in ([], ["x"] * (preparation.EMBEDDING_BATCH_SIZE + 1)):
            with self.assertRaisesRegex(ValueError, "between 1 and the configured limit"):
                preparation._embed(texts, embedder)
        self.assertEqual(embedder.calls, [])

    def test_invalid_input_fails_before_embedder_or_database_access(self):
        with (
            patch.object(preparation, "_load_items", side_effect=ValueError("invalid CSV")),
            patch.object(preparation, "_load_embedder") as load,
            patch.object(preparation, "_publish_tables") as publish,
        ):
            with self.assertRaisesRegex(ValueError, "invalid CSV"):
                preparation.poblar_catalogo()

        load.assert_not_called()
        publish.assert_not_called()

    def test_invalid_minsa_identity_fails_before_embedding_or_database_access(self):
        with (
            patch.object(preparation, "_load_items", return_value=[item_row(1)]) as load_items,
            patch.object(preparation, "_load_minsa", side_effect=ValueError("invalid MINSA identity")) as load_minsa,
            patch.object(preparation, "_load_embedder") as load,
            patch.object(preparation, "_publish_tables") as publish,
        ):
            with self.assertRaisesRegex(ValueError, "invalid MINSA identity"):
                preparation.poblar_catalogo()

        load_items.assert_called_once()
        load_minsa.assert_called_once()
        load.assert_not_called()
        publish.assert_not_called()

    def test_inconsistent_dimensions_leave_tables_unpublished(self):
        minsa = [{"row_id": "minsa:id", "CodigoMed": "06385", "NombreMed": "Medicine"}]
        database = FakeDatabase()
        embedder = FakeEmbedder(lambda texts, _call: [[1.0, 2.0], [1.0]])
        with (
            patch.dict(sys.modules, fake_database_modules(database)),
            patch.dict(os.environ, {"FASTEMBED_MODEL": MODEL}),
            patch.object(preparation, "_load_items", return_value=[item_row(1), item_row(2)]),
            patch.object(preparation, "_load_minsa", return_value=minsa),
            embedder_patches(embedder),
            patch.object(preparation, "_write_active_manifest") as activate,
        ):
            with self.assertRaisesRegex(ValueError, "inconsistent embedding dimensions"):
                preparation.poblar_catalogo(db_path=Path("unused-db"))
        activate.assert_not_called()

    def test_embedding_output_requires_complete_finite_vectors(self):
        malformed = [
            ("wrong count", lambda _texts, _call: [], "incomplete embedding batch"),
            ("empty vector", lambda _texts, _call: [[]], "empty embedding"),
            ("non-finite vector", lambda _texts, _call: [[float("nan")]], "non-finite or non-numeric"),
            ("non-numeric vector", lambda _texts, _call: [["x"]], "non-finite or non-numeric"),
        ]
        for name, factory, message in malformed:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                preparation._embed(["text"], FakeEmbedder(factory))

    def test_different_catalog_dimensions_are_rejected_without_activating_generation(self):
        items = [item_row(1)]
        minsa = [{"row_id": "minsa:id", "CodigoMed": "06385", "NombreMed": "Medicine"}]
        database = FakeDatabase()
        modules = fake_database_modules(database)

        def dimensions_by_request(texts, call_number):
            dimension = 2 if call_number == 0 else 3
            return [[1.0] * dimension for _ in texts]

        embedder = FakeEmbedder(dimensions_by_request)
        with (
            patch.dict(sys.modules, modules),
            patch.dict(os.environ, {"FASTEMBED_MODEL": MODEL}),
            patch.object(preparation, "_load_items", return_value=items),
            patch.object(preparation, "_load_minsa", return_value=minsa),
            embedder_patches(embedder),
            patch.object(preparation, "_write_active_manifest") as activate,
        ):
            with self.assertRaisesRegex(ValueError, "different dimensions"):
                preparation.poblar_catalogo(db_path=Path("unused-db"))

        activate.assert_not_called()
        self.assertEqual(len(database.calls), 1)
        self.assertEqual(database.calls[0][1], "create")

    def test_second_generation_write_failure_keeps_previous_manifest(self):
        database = FakeDatabase(fail_at=2)
        database.tables = {
            "catalogo_items__old": "previous items",
            "catalogo_minsa__old": "previous MINSA",
        }
        previous_manifest = {
            "generation": "old",
            "items_table": "catalogo_items__old",
            "minsa_table": "catalogo_minsa__old",
        }
        pointer = previous_manifest.copy()
        items, minsa = publication_rows()
        modules = fake_database_modules(database)

        with (
            patch.dict(sys.modules, modules),
            patch.object(preparation.uuid, "uuid4", return_value=SimpleNamespace(hex="new")),
            patch.object(
                preparation,
                "_write_active_manifest",
                side_effect=lambda _path, manifest: (pointer.clear(), pointer.update(manifest)),
            ) as activate,
        ):
            with self.assertRaisesRegex(RuntimeError, "table write failed"):
                preparation._publish_tables(Path("unused-db"), [items], [minsa], len(items), len(minsa))

        activate.assert_not_called()
        self.assertEqual(pointer, previous_manifest)
        self.assertIn("catalogo_items__old", database.tables)
        self.assertEqual(database.calls[0], ("catalogo_items__new", "create"))

    def test_successful_generation_points_manifest_to_both_tables(self):
        database = FakeDatabase()
        pointer = {}
        items, minsa = publication_rows()
        modules = fake_database_modules(database)

        with (
            patch.dict(sys.modules, modules),
            patch.object(preparation.uuid, "uuid4", return_value=SimpleNamespace(hex="new")),
            patch.object(
                preparation,
                "_write_active_manifest",
                side_effect=lambda _path, manifest: pointer.update(manifest),
            ) as activate,
        ):
            preparation._publish_tables(Path("unused-db"), [items], [minsa], len(items), len(minsa))

        self.assertEqual(
            database.calls,
            [("catalogo_items__new", "create"), ("catalogo_minsa__new", "create")],
        )
        activate.assert_called_once()
        self.assertEqual(pointer["generation"], "new")
        self.assertEqual(pointer["items_table"], database.calls[0][0])
        self.assertEqual(pointer["minsa_table"], database.calls[1][0])
        self.assertEqual(pointer["embedding_model"], MODEL)
        self.assertEqual(pointer["embedding_profile"], preparation.EMBEDDING_PROFILE)
        self.assertEqual(pointer["embedding_dimension"], 2)
        self.assertEqual(pointer["embedding_schema_version"], 1)

    def test_manifest_writer_atomically_replaces_after_file_sync(self):
        stream = MagicMock()
        stream.name = "/virtual-db/.active-catalogs-test.tmp"
        stream.__enter__.return_value = stream
        events = []
        stream.flush.side_effect = lambda: events.append("flush")
        stream.fileno.return_value = 9
        stream.__exit__.side_effect = lambda *_args: events.append("close")
        manifest = {"generation": "new"}

        with (
            patch.object(preparation.tempfile, "NamedTemporaryFile", return_value=stream) as temporary,
            patch.object(preparation.json, "dump", side_effect=lambda *_args, **_kwargs: events.append("dump")),
            patch.object(preparation.os, "fsync", side_effect=lambda _fd: events.append("fsync")),
            patch.object(preparation.os, "replace", side_effect=lambda *_args: events.append("replace")) as replace,
        ):
            preparation._write_active_manifest(Path("/virtual-db"), manifest)

        self.assertEqual(events, ["dump", "flush", "fsync", "close", "replace"])
        temporary.assert_called_once()
        replace.assert_called_once_with(
            stream.name, Path("/virtual-db") / preparation.ACTIVE_MANIFEST
        )


if __name__ == "__main__":
    unittest.main()
