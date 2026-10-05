"""Read-only MCP lookup over precomputed LanceDB catalog vectors."""

import os

os.environ["FASTMCP_ENV_FILE"] = os.devnull
os.environ["FASTMCP_CHECK_FOR_UPDATES"] = "off"

import json
import logging
import math
import re
from numbers import Real
from pathlib import Path
from typing import Any

import lancedb
from fastmcp import FastMCP

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "datos_medicos_db"
GUIDANCE_PATH = ROOT / "homologacion_guia.json"
MANIFEST_NAME = "active_catalogs.json"
ITEMS_TABLE_PREFIX = "catalogo_items__"
MINSA_TABLE_PREFIX = "catalogo_minsa__"
EMBEDDING_PROFILE = "homologacion-text-v1"
EMBEDDING_SCHEMA_VERSION = 1
METADATA_FIELDS = (
    "embedding_model",
    "embedding_profile",
    "embedding_dimension",
    "embedding_schema_version",
)
MINSA_FIELDS = ("row_id", "CodigoMed", "NombreMed")
ITEM_FIELDS = (
    "row_id",
    "Coditem",
    "Item",
    "CodSubFamilia",
    "SubFamilia",
    "CodAgrupador",
    "Agrupador",
)
MAX_CODE_LENGTH = 128
MAX_ROW_IDS = 5
MAX_CANDIDATES = 20
MAX_MANIFEST_BYTES = 16 * 1024
MAX_GUIDANCE_BYTES = 16 * 1024
MAX_GUIDANCE_TEXT_LENGTH = 160
MAX_EMBEDDING_DIMENSION = 65536

mcp = FastMCP("catalogo-medico")


class CatalogError(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CatalogError("incompatible", "Active catalog manifest is not an object.")
    generation = value.get("generation")
    if not isinstance(generation, str) or re.fullmatch(r"[0-9a-f]{32}", generation) is None:
        raise CatalogError("incompatible", "Active catalog generation is invalid.")
    if value.get("items_table") != f"{ITEMS_TABLE_PREFIX}{generation}" or value.get(
        "minsa_table"
    ) != f"{MINSA_TABLE_PREFIX}{generation}":
        raise CatalogError("incompatible", "Active tables do not match the manifest generation.")

    model = value.get("embedding_model")
    if not isinstance(model, str) or not model or len(model) > 256:
        raise CatalogError("incompatible", "Active embedding model metadata is invalid.")
    dimension = value.get("embedding_dimension")
    if type(dimension) is not int or not 1 <= dimension <= MAX_EMBEDDING_DIMENSION:
        raise CatalogError("incompatible", "Active embedding dimension is invalid.")
    if value.get("embedding_profile") != EMBEDDING_PROFILE:
        raise CatalogError("incompatible", "Active embedding profile is incompatible.")
    if type(value.get("embedding_schema_version")) is not int or value[
        "embedding_schema_version"
    ] != EMBEDDING_SCHEMA_VERSION:
        raise CatalogError("incompatible", "Active embedding schema version is incompatible.")
    return value


def _validate_row_metadata(row: dict[str, Any], manifest: dict[str, Any]) -> None:
    for field in METADATA_FIELDS:
        value = row.get(field)
        expected = manifest[field]
        if field in {"embedding_dimension", "embedding_schema_version"}:
            if type(value) is not int:
                raise CatalogError("incompatible", f"Catalog row has invalid {field} metadata.")
        elif not isinstance(value, str):
            raise CatalogError("incompatible", f"Catalog row has invalid {field} metadata.")
        if value != expected:
            raise CatalogError("incompatible", f"Catalog row {field} does not match the active manifest.")


def _validate_table_schema(table: Any, fields: tuple[str, ...]) -> None:
    names = getattr(getattr(table, "schema", None), "names", None)
    if not isinstance(names, list) or not set(fields + METADATA_FIELDS + ("vector",)).issubset(names):
        raise CatalogError("incompatible", "An active catalog table has an incompatible schema.")


def _open_catalog() -> tuple[dict[str, Any], Any, Any]:
    if not DB_PATH.is_dir():
        raise CatalogError("unprepared", "Prepared catalog directory is missing.")
    manifest_path = DB_PATH / MANIFEST_NAME
    if not manifest_path.is_file():
        raise CatalogError("unprepared", "Prepared catalog manifest is missing.")
    try:
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise CatalogError("incompatible", "Active catalog manifest is too large.")
        manifest = _validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    except CatalogError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogError("incompatible", "Active catalog manifest cannot be read.") from exc

    try:
        database = lancedb.connect(str(DB_PATH))
        names = set(database.list_tables().tables)
    except Exception as exc:
        raise CatalogError("unavailable", "Prepared catalog database cannot be opened.") from exc
    if manifest["items_table"] not in names or manifest["minsa_table"] not in names:
        raise CatalogError("unprepared", "An active catalog table is missing.")
    try:
        items = database.open_table(manifest["items_table"])
        minsa = database.open_table(manifest["minsa_table"])
    except Exception as exc:
        raise CatalogError("unavailable", "An active catalog table cannot be opened.") from exc
    _validate_table_schema(items, ITEM_FIELDS)
    _validate_table_schema(minsa, MINSA_FIELDS)
    return manifest, items, minsa


def _catalog_failure(exc: CatalogError) -> dict[str, Any]:
    return {"status": exc.status, "error": exc.message}


def _query_rows(
    table: Any, where: str, fields: tuple[str, ...], limit: int, *, include_vector: bool = True
) -> list[dict[str, Any]]:
    selected = fields + METADATA_FIELDS + (("vector",) if include_vector else ())
    return table.search(query_type="vector").where(where).select(list(selected)).limit(limit).to_list()


def _valid_code(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= MAX_CODE_LENGTH
        and bool(value.strip())
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _valid_limit(value: Any, maximum: int) -> bool:
    return type(value) is int and 1 <= value <= maximum


def _sql_string(value: str) -> str:
    # The column name is constant; quote embedded apostrophes in the scalar value.
    return "'" + value.replace("'", "''") + "'"


def _vector(row: dict[str, Any], dimension: int) -> list[float]:
    value = row.get("vector")
    if not isinstance(value, (list, tuple)) or len(value) != dimension:
        raise CatalogError("incompatible", "Catalog row vector has an incompatible dimension.")
    if any(not isinstance(item, Real) or isinstance(item, bool) or not math.isfinite(item) for item in value):
        raise CatalogError("incompatible", "Catalog row vector contains invalid values.")
    return [float(item) for item in value]


def _text_fields(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, str]:
    result = {}
    for field in fields:
        value = row.get(field)
        if not isinstance(value, str):
            raise CatalogError("incompatible", f"Catalog row has invalid {field} data.")
        result[field] = value
    return result


def _valid_guidance_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= MAX_GUIDANCE_TEXT_LENGTH
        and bool(value.strip())
        and not any(
            ord(char) < 32 or 0x7F <= ord(char) < 0xA0 or 0xD800 <= ord(char) <= 0xDFFF
            for char in value
        )
    )


def _validate_guidance(value: Any) -> dict[str, Any]:
    required = {"schema_version", "review_fields", "by_agrupador"}
    allowed = required | {"aliases"}
    if (
        not isinstance(value, dict)
        or not required.issubset(value)
        or not set(value).issubset(allowed)
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
    ):
        raise CatalogError("incompatible", "Local homologation guidance has an invalid schema.")

    review_fields = value["review_fields"]
    aliases = value.get("aliases", {})
    by_agrupador = value["by_agrupador"]
    if (
        not isinstance(review_fields, list)
        or not review_fields
        or not all(_valid_guidance_text(item) for item in review_fields)
        or not isinstance(aliases, dict)
        or not all(_valid_guidance_text(key) and _valid_guidance_text(item) for key, item in aliases.items())
        or not isinstance(by_agrupador, dict)
        or not all(
            _valid_guidance_text(key)
            and isinstance(checklist, list)
            and all(_valid_guidance_text(item) for item in checklist)
            for key, checklist in by_agrupador.items()
        )
    ):
        raise CatalogError("incompatible", "Local homologation guidance has an invalid schema.")
    return value


def _load_guidance() -> dict[str, Any]:
    try:
        with GUIDANCE_PATH.open("rb") as stream:
            raw = stream.read(MAX_GUIDANCE_BYTES + 1)
    except FileNotFoundError as exc:
        raise CatalogError("unprepared", "Local homologation guidance file is missing.") from exc
    except OSError as exc:
        raise CatalogError("unavailable", "Local homologation guidance file cannot be read.") from exc
    if len(raw) > MAX_GUIDANCE_BYTES:
        raise CatalogError("incompatible", "Local homologation guidance file is too large.")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogError("incompatible", "Local homologation guidance is not valid UTF-8 JSON.") from exc
    return _validate_guidance(value)


@mcp.tool()
def buscar_minsa_por_codigo(codigo_med: str, limite: int = 10) -> dict[str, Any]:
    """Look up prepared MINSA IDs by exact CodigoMed without generating embeddings."""
    if not _valid_code(codigo_med):
        return {"status": "invalid_input", "error": "codigo_med must be non-empty, text, and at most 128 characters."}
    if not _valid_limit(limite, MAX_CANDIDATES):
        return {"status": "invalid_input", "error": f"limite must be between 1 and {MAX_CANDIDATES}."}
    try:
        manifest, _, minsa = _open_catalog()
        rows = _query_rows(
            minsa,
            f"CodigoMed = {_sql_string(codigo_med)}",
            MINSA_FIELDS,
            limite,
            include_vector=False,
        )
        results = []
        for row in rows:
            _validate_row_metadata(row, manifest)
            results.append(_text_fields(row, MINSA_FIELDS))
        return {
            "status": "ok" if results else "not_found",
            "generation": manifest["generation"],
            "results": results,
            "limit_reached": len(results) == limite,
        }
    except CatalogError as exc:
        return _catalog_failure(exc)
    except Exception:
        logging.exception("MINSA code lookup failed")
        return {"status": "unavailable", "error": "Catalog lookup failed."}


@mcp.tool()
def buscar_candidatos(row_ids: list[str], limite: int = 5) -> dict[str, Any]:
    """Retrieve bounded internal candidates using stored MINSA vectors only."""
    if (
        not isinstance(row_ids, list)
        or not 1 <= len(row_ids) <= MAX_ROW_IDS
        or any(not isinstance(row_id, str) or re.fullmatch(r"minsa:[0-9a-f]{64}", row_id) is None for row_id in row_ids)
        or len(set(row_ids)) != len(row_ids)
    ):
        return {
            "status": "invalid_input",
            "error": f"row_ids must contain 1 to {MAX_ROW_IDS} unique prepared MINSA IDs.",
        }
    if not _valid_limit(limite, MAX_CANDIDATES):
        return {"status": "invalid_input", "error": f"limite must be between 1 and {MAX_CANDIDATES}."}

    try:
        manifest, items, minsa = _open_catalog()
        quoted_ids = ", ".join(_sql_string(row_id) for row_id in row_ids)
        external_rows = _query_rows(
            minsa,
            f"row_id IN ({quoted_ids})",
            MINSA_FIELDS,
            len(row_ids),
        )
        by_id = {}
        for row in external_rows:
            _validate_row_metadata(row, manifest)
            external = _text_fields(row, MINSA_FIELDS)
            by_id[external["row_id"]] = (external, _vector(row, manifest["embedding_dimension"]))
        missing = [row_id for row_id in row_ids if row_id not in by_id]
        results = []
        for row_id in row_ids:
            if row_id not in by_id:
                continue
            external, vector = by_id[row_id]
            candidates = (
                items.search(vector, vector_column_name="vector", query_type="vector")
                .select(list(ITEM_FIELDS + METADATA_FIELDS + ("_distance",)))
                .limit(limite)
                .to_list()
            )
            formatted = []
            for rank, row in enumerate(candidates, start=1):
                _validate_row_metadata(row, manifest)
                candidate = _text_fields(row, ITEM_FIELDS)
                distance = row.get("_distance", row.get("distance"))
                if not isinstance(distance, Real) or isinstance(distance, bool) or not math.isfinite(distance):
                    raise CatalogError("incompatible", "Internal candidate has invalid vector distance.")
                formatted.append(
                    {
                        **candidate,
                        "rank": rank,
                        "distance": float(distance),
                        "method": "vector",
                        "decision": "review",
                    }
                )
            results.append({**external, "candidates": formatted})
        return {
            "status": "ok" if results else "not_found",
            "generation": manifest["generation"],
            "results": results,
            "missing_row_ids": missing,
        }
    except CatalogError as exc:
        return _catalog_failure(exc)
    except Exception:
        logging.exception("Offline candidate lookup failed")
        return {"status": "unavailable", "error": "Catalog lookup failed."}


@mcp.tool()
def obtener_guia_homologacion() -> dict[str, Any]:
    """Read bounded, local declarative guidance for homologation review."""
    try:
        return {"status": "ok", "guidance": _load_guidance()}
    except CatalogError as exc:
        return _catalog_failure(exc)
    except Exception:
        logging.exception("Homologation guidance lookup failed")
        return {"status": "unavailable", "error": "Guidance lookup failed."}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="stdio")
