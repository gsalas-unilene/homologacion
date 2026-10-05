import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

if importlib.util.find_spec("fastmcp") is None:
    fastmcp_stub = types.ModuleType("fastmcp")

    class FastMCP:
        def __init__(self, name):
            self.name = name

        def tool(self):
            return lambda function: function

    fastmcp_stub.FastMCP = FastMCP
    sys.modules["fastmcp"] = fastmcp_stub

import mcp_server
import lancedb


GENERATION = "a" * 32
MODEL = "qwen3-embedding:latest"
PROFILE = "homologacion-text-v1"
METADATA = {
    "embedding_model": MODEL,
    "embedding_profile": PROFILE,
    "embedding_dimension": 2,
    "embedding_schema_version": 1,
}
MINSA_ID = "minsa:" + "b" * 64


class FakeDatabase:
    def list_tables(self):
        return SimpleNamespace(tables=[f"catalogo_items__{GENERATION}"])

    def open_table(self, name):
        raise AssertionError(f"unexpected table open: {name}")


def manifest():
    return {
        "generation": GENERATION,
        "items_table": f"catalogo_items__{GENERATION}",
        "minsa_table": f"catalogo_minsa__{GENERATION}",
        **METADATA,
    }


def create_catalog(path, *, bad_item_metadata=False):
    import pyarrow as pa

    path.mkdir()
    (path / "active_catalogs.json").write_text(json.dumps(manifest()), encoding="utf-8")
    database = lancedb.connect(str(path))
    metadata_fields = [
        pa.field("embedding_model", pa.string()),
        pa.field("embedding_profile", pa.string()),
        pa.field("embedding_dimension", pa.int32()),
        pa.field("embedding_schema_version", pa.int32()),
    ]
    minsa_schema = pa.schema(
        [
            pa.field("row_id", pa.string()),
            pa.field("CodigoMed", pa.string()),
            pa.field("NombreMed", pa.string()),
            *metadata_fields,
            pa.field("vector", pa.list_(pa.float32())),
        ]
    )
    item_schema = pa.schema(
        [
            pa.field("row_id", pa.string()),
            pa.field("Coditem", pa.string()),
            pa.field("Item", pa.string()),
            pa.field("CodSubFamilia", pa.string()),
            pa.field("SubFamilia", pa.string()),
            pa.field("CodAgrupador", pa.string()),
            pa.field("Agrupador", pa.string()),
            *metadata_fields,
            pa.field("vector", pa.list_(pa.float32())),
        ]
    )
    minsa_row = {
        "row_id": MINSA_ID,
        "CodigoMed": "001234",
        "NombreMed": "Nombre fuente exacto",
        **METADATA,
        "vector": [0.25, 0.75],
    }
    item_row = {
        "row_id": "INT-9",
        "Coditem": "INT-9",
        "Item": "Producto interno",
        "CodSubFamilia": "SF-2",
        "SubFamilia": "Subfamilia",
        "CodAgrupador": "AG-1",
        "Agrupador": "Agrupador",
        **METADATA,
        "vector": [0.2, 0.8],
    }
    if bad_item_metadata:
        item_row["embedding_profile"] = "other-profile"
    database.create_table(
        f"catalogo_minsa__{GENERATION}",
        data=pa.Table.from_pylist([minsa_row], schema=minsa_schema),
    )
    database.create_table(
        f"catalogo_items__{GENERATION}",
        data=pa.Table.from_pylist([item_row], schema=item_schema),
    )


class MCPServerTests(unittest.TestCase):
    def test_fastmcp_import_guard_disables_dotenv_and_update_checks(self):
        fastmcp_settings = getattr(sys.modules["fastmcp"], "settings", None)
        if fastmcp_settings is None:
            self.skipTest("FastMCP settings are unavailable")

        self.assertEqual(os.environ["FASTMCP_ENV_FILE"], os.devnull)
        self.assertEqual(os.environ["FASTMCP_CHECK_FOR_UPDATES"], "off")
        self.assertEqual(fastmcp_settings.check_for_updates, "off")

    def test_lookup_and_candidates_use_precomputed_vectors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog"
            create_catalog(path)
            with patch.object(mcp_server, "DB_PATH", path):
                found = mcp_server.buscar_minsa_por_codigo("001234")
                self.assertEqual(found["status"], "ok")
                self.assertEqual(found["results"], [{
                    "row_id": MINSA_ID,
                    "CodigoMed": "001234",
                    "NombreMed": "Nombre fuente exacto",
                }])

                response = mcp_server.buscar_candidatos([MINSA_ID], limite=1)

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["missing_row_ids"], [])
        result = response["results"][0]
        self.assertEqual(result["CodigoMed"], "001234")
        self.assertEqual(result["NombreMed"], "Nombre fuente exacto")
        candidate = result["candidates"][0]
        self.assertEqual(
            {key: value for key, value in candidate.items() if key != "distance"},
            {
                "row_id": "INT-9",
                "Coditem": "INT-9",
                "Item": "Producto interno",
                "CodSubFamilia": "SF-2",
                "SubFamilia": "Subfamilia",
                "CodAgrupador": "AG-1",
                "Agrupador": "Agrupador",
                "rank": 1,
                "method": "vector",
                "decision": "review",
            },
        )
        self.assertIsInstance(candidate["distance"], float)
        self.assertGreaterEqual(candidate["distance"], 0.0)

    def test_in_process_client_uses_prepared_catalog(self):
        try:
            from fastmcp import Client
        except ImportError:
            self.skipTest("FastMCP Client is unavailable")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog"
            create_catalog(path)

            async def exercise_client():
                with patch.object(mcp_server, "DB_PATH", path):
                    async with Client(mcp_server.mcp) as client:
                        tools = await client.list_tools()
                        tool_names = {tool.name for tool in tools}
                        self.assertTrue(
                            {"buscar_minsa_por_codigo", "buscar_candidatos", "obtener_guia_homologacion"}
                            <= tool_names
                        )

                        guidance = await client.call_tool("obtener_guia_homologacion", {})
                        self.assertFalse(guidance.is_error)
                        self.assertEqual(guidance.data["status"], "ok")
                        self.assertEqual(
                            guidance.data["guidance"],
                            {
                                "schema_version": 1,
                                "aliases": {},
                                "review_fields": ["material", "measure", "unit", "concentration"],
                                "by_agrupador": {},
                            },
                        )

                        lookup = await client.call_tool(
                            "buscar_minsa_por_codigo", {"codigo_med": "001234"}
                        )
                        self.assertFalse(lookup.is_error)
                        self.assertIsInstance(lookup.data, dict)
                        self.assertEqual(lookup.data["status"], "ok")
                        external = lookup.data["results"][0]
                        self.assertEqual(external["CodigoMed"], "001234")

                        candidates = await client.call_tool(
                            "buscar_candidatos",
                            {"row_ids": [external["row_id"]], "limite": 1},
                        )
                        self.assertFalse(candidates.is_error)
                        self.assertIsInstance(candidates.data, dict)
                        self.assertEqual(candidates.data["status"], "ok")
                        candidate = candidates.data["results"][0]["candidates"][0]
                        self.assertEqual(candidate["Coditem"], "INT-9")
                        self.assertEqual(candidate["decision"], "review")

            asyncio.run(exercise_client())

    def test_guidance_is_bounded_and_rejects_invalid_json_or_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "homologacion_guia.json"
            with patch.object(mcp_server, "GUIDANCE_PATH", path):
                self.assertEqual(mcp_server.obtener_guia_homologacion()["status"], "unprepared")

                path.write_text("{", encoding="utf-8")
                self.assertEqual(mcp_server.obtener_guia_homologacion()["status"], "incompatible")

                minimal = {
                    "schema_version": 1,
                    "review_fields": ["material"],
                    "by_agrupador": {},
                }
                path.write_text(json.dumps(minimal), encoding="utf-8")
                self.assertEqual(
                    mcp_server.obtener_guia_homologacion()["guidance"], minimal
                )

                invalid_schemas = (
                    {**minimal, "unexpected": "value"},
                    {**minimal, "schema_version": True},
                    {**minimal, "aliases": ["not", "a", "map"]},
                    {**minimal, "by_agrupador": {"group": "not a checklist"}},
                    {**minimal, "review_fields": ["x" * (mcp_server.MAX_GUIDANCE_TEXT_LENGTH + 1)]},
                )
                for value in invalid_schemas:
                    with self.subTest(value=value):
                        path.write_text(json.dumps(value), encoding="utf-8")
                        self.assertEqual(
                            mcp_server.obtener_guia_homologacion()["status"], "incompatible"
                        )

                path.write_bytes(b" " * (mcp_server.MAX_GUIDANCE_BYTES + 1))
                self.assertEqual(mcp_server.obtener_guia_homologacion()["status"], "incompatible")

    def test_missing_active_table_is_reported_as_unprepared(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "active_catalogs.json").write_text(json.dumps(manifest()), encoding="utf-8")
            with patch.object(mcp_server, "DB_PATH", path), patch.object(
                mcp_server.lancedb, "connect", return_value=FakeDatabase()
            ):
                response = mcp_server.buscar_candidatos([MINSA_ID])
        self.assertEqual(response["status"], "unprepared")

    def test_candidate_metadata_must_match_active_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog"
            create_catalog(path, bad_item_metadata=True)
            with patch.object(mcp_server, "DB_PATH", path):
                response = mcp_server.buscar_candidatos([MINSA_ID])
        self.assertEqual(response["status"], "incompatible")

    def test_input_is_bounded_and_unknown_ids_are_explicit(self):
        self.assertEqual(mcp_server.buscar_candidatos(["minsa:bad"])["status"], "invalid_input")
        self.assertEqual(mcp_server.buscar_minsa_por_codigo("x", limite=21)["status"], "invalid_input")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog"
            create_catalog(path)
            unknown = "minsa:" + "c" * 64
            with patch.object(mcp_server, "DB_PATH", path):
                response = mcp_server.buscar_candidatos([unknown])
        self.assertEqual(response["status"], "not_found")
        self.assertEqual(response["missing_row_ids"], [unknown])


if __name__ == "__main__":
    unittest.main()
