"""Convert the Unilene CodSut dictionary workbook to ``items/codsut_estructura.json``.

Run from the repository root; openpyxl is needed only here, never at runtime:
``uv run --with openpyxl python convertir_estructura.py``. The workbook has one row per entry and nine
(code, description) column pairs; each pair becomes one code -> description dictionary.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
XLSX = ROOT / "items" / "unilene_codsut_estructura.xlsx"
JSON_PATH = ROOT / "items" / "codsut_estructura.json"
NAMES = ("marca", "hebra", "calibre", "aguja", "long_aguja", "long_hebra", "caja", "clase", "campo_variable")


def convertir(xlsx: Path = XLSX) -> dict[str, dict[str, str]]:
    import openpyxl

    sheet = openpyxl.load_workbook(xlsx, data_only=True).worksheets[0]
    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    result = {}
    for index, name in enumerate(NAMES):
        entries = {}
        for row in rows:
            code, description = row[2 * index], row[2 * index + 1]
            if code is not None and description is not None:
                entries[str(code)] = str(description).strip()
        result[name] = entries
    return result


def main() -> int:
    data = convertir()
    JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {JSON_PATH}: " + ", ".join(f"{name} {len(entries)}" for name, entries in data.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
