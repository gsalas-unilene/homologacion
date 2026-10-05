"""Bulk homologation: write the best own-product candidate for every MINSA row.

Run from the repository root with ``uv run python homologar.py [--limit N]``. It reads the active
LanceDB catalog directly with the stored vectors (no embedder, no MCP) and writes
``salida/homologacion.csv``. Tiers are candidates for human review, not clinical equivalence.
"""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

import mcp_server  # also keeps FastMCP from reading any .env file
from homologador.clasificar import COLUMNS, clasificar, es_sutura

SALIDA = Path(__file__).resolve().parent / "salida" / "homologacion.csv"
BATCH = 500
TOP = 30
NO_SUTURAS = f"Agrupador != {mcp_server._sql_string('01. SUTURAS')}"
TIERS = ("probable", "revisar", "sin_equivalente")


def homologar(salida: Path = SALIDA, limit: int | None = None) -> Counter:
    manifest, items, minsa = mcp_server._open_catalog()
    total = minsa.count_rows() if limit is None else min(limit, minsa.count_rows())
    fields = list(mcp_server.MINSA_FIELDS + mcp_server.METADATA_FIELDS + ("vector",))
    item_fields = list(mcp_server.ITEM_FIELDS + mcp_server.METADATA_FIELDS + ("_distance",))
    counts = Counter()
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, COLUMNS)
        writer.writeheader()
        for offset in range(0, total, BATCH):
            rows = minsa.search().select(fields).limit(min(BATCH, total - offset)).offset(offset).to_list()
            for row in rows:
                mcp_server._validate_row_metadata(row, manifest)
                vector = mcp_server._vector(row, manifest["embedding_dimension"])
                query = items.search(vector, vector_column_name="vector", query_type="vector")
                if not es_sutura(row["NombreMed"]):
                    # 21832 of 22668 own items are sutures and crowd the top-30; search the rest only.
                    query = query.where(NO_SUTURAS)
                candidates = query.select(item_fields).limit(TOP).to_list()
                result = clasificar(row["NombreMed"], candidates)
                result["distance"] = round(result["distance"], 4)
                writer.writerow({"CodigoMed": row["CodigoMed"], "NombreMed": row["NombreMed"], **result})
                counts[result["tier"]] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="process only the first N MINSA rows (sampling)")
    args = parser.parse_args(argv)
    try:
        counts = homologar(limit=args.limit)
    except mcp_server.CatalogError as exc:
        print(f"Catalog {exc.status}: {exc.message}", file=sys.stderr)
        return 1
    print(f"Wrote {SALIDA} ({sum(counts.values())} rows)")
    for tier in TIERS:
        print(f"{tier}: {counts[tier]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
