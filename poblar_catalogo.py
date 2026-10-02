"""Prepare offline catalog vectors for the read-only MCP.

Run from the repository root with ``python poblar_catalogo.py``. Vectors are
computed locally on CPU with FastEmbed (ONNX). ``FASTEMBED_MODEL`` is optional
in the process environment or the local ``.env`` file; the preparer reads it at
invocation time, process environment first, and only allowlisted models are
accepted. Every vector is L2-normalized because the MCP searches LanceDB with
the default L2 metric, which ranks like cosine only for unit vectors.

T2 contract: ``catalogo_items`` stores ``row_id``/``Coditem``, ``Item``,
``CodSubFamilia``, ``SubFamilia``, ``CodAgrupador``, ``Agrupador``; ``catalogo_minsa``
stores ``row_id``, ``CodigoMed`` and ``NombreMed``. Both add ``vector``,
``embedding_model``, ``embedding_profile``, ``embedding_dimension`` and
``embedding_schema_version`` per row. Profile ``homologacion-text-v1`` embeds
internal ``Item``/``SubFamilia``/``Agrupador`` and MINSA ``NombreMed``. Each
run writes generation-suffixed tables, then atomically replaces
``active_catalogs.json`` with ``generation``, ``items_table``, ``minsa_table``
and the compatibility metadata; old generations are retained. MINSA
``row_id`` is content-derived and stable across repeated preparation, not
``CodigoMed``. T2 should load the manifest and reject incompatible model,
profile, dimension or schema-version metadata. Model names such as
``FASTEMBED_DEFAULT_MODEL`` are recorded by name; recording a name does not pin
model weights or guarantee bit-for-bit reproducibility.
"""

import csv
import hashlib
import json
import logging
import math
import os
import tempfile
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ITEMS_CSV = ROOT / "items" / "items.csv"
MINSA_CSV = ROOT / "items" / "items_minsa.csv"
DB_PATH = ROOT / "datos_medicos_db"
DOTENV_PATH = ROOT / ".env"
FASTEMBED_DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
FASTEMBED_ALLOWED_MODELS = (FASTEMBED_DEFAULT_MODEL, "jinaai/jina-embeddings-v2-base-es")
# FastEmbed's default cache is the system temp dir, which gets wiped.
FASTEMBED_CACHE_DIR = ROOT / ".fastembed_cache"
EMBEDDING_THREADS = 8
EMBEDDING_PROFILE = "homologacion-text-v1"
EMBEDDING_SCHEMA_VERSION = 1
EMBEDDING_BATCH_SIZE = 64
ITEMS_TABLE = "catalogo_items"
MINSA_TABLE = "catalogo_minsa"
ACTIVE_MANIFEST = "active_catalogs.json"


def _read_csv(stream, required: set[str], source: str) -> list[dict[str, str]]:
    reader = csv.DictReader(stream, strict=True)
    if not reader.fieldnames:
        raise ValueError(f"{source} has no CSV header")
    headers = [header.strip() for header in reader.fieldnames if header is not None]
    if len(headers) != len(reader.fieldnames) or len(headers) != len(set(headers)):
        raise ValueError(f"{source} has empty or duplicate CSV headers")
    missing = required - set(headers)
    if missing:
        raise ValueError(f"{source} is missing CSV columns: {', '.join(sorted(missing))}")

    rows: list[dict[str, str]] = []
    for line, raw in enumerate(reader, start=2):
        if None in raw or any(value is None for value in raw.values()):
            raise ValueError(f"{source} has a malformed row at line {line}")
        rows.append({key.strip(): value for key, value in raw.items()})
    if not rows:
        raise ValueError(f"{source} contains no data rows")
    return rows


def _items_from_csv(stream) -> list[dict[str, str]]:
    required = {
        "Coditem", "Item", "CodSubFamilia", "SubFamilia", "CodAgrupador", "Agrupador"
    }
    rows = _read_csv(stream, required, "items.csv")
    seen: set[str] = set()
    items = []
    for line, row in enumerate(rows, start=2):
        code = row["Coditem"]
        if not code.strip() or not row["Item"].strip():
            raise ValueError(f"items.csv has an empty Coditem or Item at data row {line}")
        identity = code.strip()
        if identity in seen:
            raise ValueError(f"items.csv has duplicate Coditem {identity!r}")
        seen.add(identity)
        items.append({"row_id": code, **{key: row[key] for key in required}})
    return items


def _minsa_from_csv(stream) -> list[dict[str, str]]:
    rows = _read_csv(stream, {"CodigoMed", "NombreMed"}, "items_minsa.csv")
    occurrences: Counter[tuple[str, str]] = Counter()
    result = []
    for line, row in enumerate(rows, start=2):
        code, name = row["CodigoMed"], row["NombreMed"]
        if not code.strip():
            raise ValueError(f"items_minsa.csv has an empty CodigoMed at data row {line}")
        if not name.strip():
            logging.warning("Excluding MINSA CodigoMed=%s: NombreMed is empty", code)
            continue
        signature = (code, name)
        occurrences[signature] += 1
        digest = hashlib.sha256(
            f"{code}\0{name}\0{occurrences[signature]}".encode("utf-8")
        ).hexdigest()
        result.append({"row_id": f"minsa:{digest}", "CodigoMed": code, "NombreMed": name})
    if not result:
        raise ValueError("items_minsa.csv contains no usable rows")
    return result


def _load_items(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return _items_from_csv(stream)


def _load_minsa(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return _minsa_from_csv(stream)


def _load_fastembed_model() -> str:
    # Import and read dotenv only during the supervised preparation call.
    from dotenv import dotenv_values

    file_values = dotenv_values(DOTENV_PATH)
    model = os.environ.get("FASTEMBED_MODEL", file_values.get("FASTEMBED_MODEL"))
    if model is None or not model.strip():
        return FASTEMBED_DEFAULT_MODEL
    model = model.strip()
    if model not in FASTEMBED_ALLOWED_MODELS:
        raise ValueError(
            "FASTEMBED_MODEL must be one of: " + ", ".join(FASTEMBED_ALLOWED_MODELS)
        )
    return model


def _load_embedder(model: str):
    # Single seam for tests: the lazy import keeps fastembed out of module import.
    from fastembed import TextEmbedding

    return TextEmbedding(model, cache_dir=str(FASTEMBED_CACHE_DIR), threads=EMBEDDING_THREADS)


def _write_active_manifest(db_path: Path, manifest: dict[str, object]) -> None:
    path = db_path / ACTIVE_MANIFEST
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=db_path, prefix=".active-catalogs-", suffix=".tmp", delete=False
    ) as stream:
        json.dump(manifest, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(stream.name, path)


def _publish_tables(db_path: Path, item_batches, minsa_batches, item_count: int, minsa_count: int) -> None:
    import lancedb
    import pyarrow as pa

    metadata_fields = (
        "embedding_model",
        "embedding_profile",
        "embedding_dimension",
        "embedding_schema_version",
    )
    metadata = [
        pa.field("embedding_model", pa.string()),
        pa.field("embedding_profile", pa.string()),
        pa.field("embedding_dimension", pa.int32()),
        pa.field("embedding_schema_version", pa.int32()),
    ]
    items_schema = pa.schema(
        [
            pa.field("row_id", pa.string()),
            pa.field("Coditem", pa.string()),
            pa.field("Item", pa.string()),
            pa.field("CodSubFamilia", pa.string()),
            pa.field("SubFamilia", pa.string()),
            pa.field("CodAgrupador", pa.string()),
            pa.field("Agrupador", pa.string()),
            *metadata,
            pa.field("vector", pa.list_(pa.float32())),
        ]
    )
    minsa_schema = pa.schema(
        [
            pa.field("row_id", pa.string()),
            pa.field("CodigoMed", pa.string()),
            pa.field("NombreMed", pa.string()),
            *metadata,
            pa.field("vector", pa.list_(pa.float32())),
        ]
    )
    generation = uuid.uuid4().hex
    items_name = f"{ITEMS_TABLE}__{generation}"
    minsa_name = f"{MINSA_TABLE}__{generation}"
    database = lancedb.connect(str(db_path))

    def append_batches(table_name, batches, schema, expected_count, label, expected_metadata=None):
        table = None
        row_count = 0
        table_metadata = None
        for rows in batches:
            if not rows or len(rows) > EMBEDDING_BATCH_SIZE:
                raise ValueError("Embedder returned an invalid embedding batch size")
            batch_metadata = tuple(rows[0][field] for field in metadata_fields)
            if any(
                tuple(row[field] for field in metadata_fields) != batch_metadata
                for row in rows
            ):
                raise ValueError("Embedding metadata changed within a batch")
            if table_metadata is None:
                table_metadata = batch_metadata
                if expected_metadata is not None and table_metadata != expected_metadata:
                    raise ValueError("Embedder returned different dimensions for the two catalogs")
            elif batch_metadata != table_metadata:
                raise ValueError("Embedding metadata changed between batches")

            arrow_table = pa.Table.from_pylist(rows, schema=schema)
            if table is None:
                table = database.create_table(table_name, data=arrow_table, mode="create")
            else:
                table.add(arrow_table)
            row_count += len(rows)
            logging.info("Wrote %d/%d %s catalog rows", row_count, expected_count, label)
            del arrow_table, rows

        if table is None or row_count != expected_count:
            raise ValueError(f"Incomplete {label} catalog generation")
        return table_metadata

    item_metadata = append_batches(
        items_name, item_batches, items_schema, item_count, "internal"
    )
    append_batches(
        minsa_name, minsa_batches, minsa_schema, minsa_count, "MINSA", item_metadata
    )
    _write_active_manifest(
        db_path,
        {
            "generation": generation,
            "items_table": items_name,
            "minsa_table": minsa_name,
            **dict(zip(metadata_fields, item_metadata, strict=True)),
        },
    )


def _embed(texts: list[str], embedder) -> list[list[float]]:
    if not texts or len(texts) > EMBEDDING_BATCH_SIZE:
        raise ValueError("Embedding request batch must be between 1 and the configured limit")
    embeddings = [
        vector.tolist() if hasattr(vector, "tolist") else vector
        for vector in embedder.embed(texts)
    ]
    if len(embeddings) != len(texts):
        raise ValueError("Embedder returned an incomplete embedding batch")

    dimension: int | None = None
    for embedding in embeddings:
        if not isinstance(embedding, list) or not embedding:
            raise ValueError("Embedder returned an empty embedding")
        if dimension is not None and len(embedding) != dimension:
            raise ValueError("Embedder returned inconsistent embedding dimensions")
        dimension = len(embedding)
        for value in embedding:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError("Embedder returned a non-finite or non-numeric embedding")
            try:
                finite_value = float(value)
            except (OverflowError, ValueError):
                raise ValueError("Embedder returned a non-finite or non-numeric embedding") from None
            if not math.isfinite(finite_value):
                raise ValueError("Embedder returned a non-finite or non-numeric embedding")

    normalized = []
    for embedding in embeddings:
        norm = math.hypot(*embedding)
        if norm == 0.0 or not math.isfinite(norm):
            raise ValueError("Embedder returned a zero-norm embedding")
        normalized.append([value / norm for value in embedding])
    return normalized


def _with_vectors(records, vectors, model, dimension):
    return [
        {
            **record,
            "embedding_model": model,
            "embedding_profile": EMBEDDING_PROFILE,
            "embedding_dimension": dimension,
            "embedding_schema_version": EMBEDDING_SCHEMA_VERSION,
            "vector": vector,
        }
        for record, vector in zip(records, vectors, strict=True)
    ]


def _embedded_row_batches(records, model, embedder, text_for_row):
    dimension = None
    for start in range(0, len(records), EMBEDDING_BATCH_SIZE):
        source_batch = records[start : start + EMBEDDING_BATCH_SIZE]
        texts = [text_for_row(row) for row in source_batch]
        vectors = _embed(texts, embedder)
        batch_dimension = len(vectors[0])
        if dimension is not None and batch_dimension != dimension:
            raise ValueError("Embedder returned inconsistent embedding dimensions")
        dimension = batch_dimension
        rows = _with_vectors(source_batch, vectors, model, dimension)
        del source_batch, texts, vectors
        yield rows
        del rows


def poblar_catalogo(
    items_path: Path = ITEMS_CSV,
    minsa_path: Path = MINSA_CSV,
    db_path: Path = DB_PATH,
) -> None:
    # Parse and validate both complete inputs before requesting embeddings or touching LanceDB.
    items = _load_items(Path(items_path))
    minsa = _load_minsa(Path(minsa_path))
    model = _load_fastembed_model()
    embedder = _load_embedder(model)

    _publish_tables(
        Path(db_path),
        _embedded_row_batches(
            items,
            model,
            embedder,
            lambda row: " | ".join(
                value for value in (row["Item"], row["SubFamilia"], row["Agrupador"])
                if value.strip()
            ),
        ),
        _embedded_row_batches(minsa, model, embedder, lambda row: row["NombreMed"]),
        len(items),
        len(minsa),
    )
    logging.info("Indexed %d internal and %d MINSA rows", len(items), len(minsa))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        poblar_catalogo()
    except Exception:
        logging.exception("Could not build the offline catalogs")
        raise SystemExit(1) from None
