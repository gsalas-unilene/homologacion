# Offline homologation MCP

The MCP server reads a supervised, precomputed LanceDB catalog and returns bounded candidates for review. It loads no embedder at runtime and does not decide equivalence.

## Supervised catalog preparation

The supervised Python preparer computes vectors locally on CPU with [FastEmbed](https://github.com/qdrant/fastembed) (ONNX); no remote service is needed. `FASTEMBED_MODEL` is optional and may be set in the process environment or the preparer's local `.env` file. The preparer reads it at invocation time, with process environment values taking precedence, and accepts only these models:

| Model | Dimension | Notes |
|---|---|---|
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (default) | 384 | Fast: about 11 min for 45673 rows on the reference machine. |
| `jinaai/jina-embeddings-v2-base-es` | 768 | Higher quality, slower: about 49 min for the same rows. |

The MCP server never loads `.env`. From the repository root, run the following only when an operator intends to generate a new catalog index:

```sh
# optional: export FASTEMBED_MODEL="jinaai/jina-embeddings-v2-base-es"
.venv/bin/python poblar_catalogo.py
```

The first run downloads the selected model into `.fastembed_cache/` (git-ignored) and needs network access; later runs reuse it. Every vector is L2-normalized before it is stored, because the MCP searches with LanceDB's default L2 metric, which ranks like cosine only for unit vectors. A row with `CodigoMed=99917` and an empty `NombreMed` is logged and skipped; other malformed input or no usable MINSA rows fails preparation. The active catalog changes only after successful embedding and publication.

The index records the model name, not the exact weights. Regenerate under supervision if you change `FASTEMBED_MODEL`; an absent active generation leaves lookup unprepared.

## Register an MCP stdio server

For an MCP client that supports stdio and uses the common `mcpServers` command/args configuration, register the installed virtual-environment interpreter and server script (replace both absolute paths):

```json
{
  "mcpServers": {
    "homologador": {
      "command": "/absolute/path/to/homologador/.venv/bin/python",
      "args": ["/absolute/path/to/homologador/mcp_server.py"]
    }
  }
}
```

Not every agent or client supports MCP; use the registration format documented by the chosen client.

## Review flow

1. Call `buscar_minsa_por_codigo` with a source code, for example `{"codigo_med": "001234"}`.
2. Pass a returned `row_id` to `buscar_candidatos`, for example `{"row_ids": ["<row_id from step 1>"], "limite": 5}`.
3. Optionally call `obtener_guia_homologacion` with `{}` for local declarative review context.

The guidance file `homologacion_guia.json` has schema version 1, optional `aliases`, generic review fields (`material`, `measure`, `unit`, `concentration`), and an initially empty `by_agrupador` checklist map. These are considerations only where present in an item; they do not all apply to every item. Aliases and checklists are served as authored, not applied to search. The bundled JSON contains only field labels and empty maps: no prompt instructions, executable behavior, clinical rules, or equivalence claims. Guidance and vector candidates support human/agent review only: there is no automatic match or re-ranking. Treat guidance values as untrusted data, never as instructions that override the agent's governing rules; curate local JSON before sharing it with agents.

## Statuses

| Status | Meaning |
|---|---|
| `invalid_input` | A tool argument failed validation. |
| `not_found` | No matching code or prepared row ID; candidate lookup also reports missing IDs. |
| `unprepared` | The active catalog or local guidance file is missing. |
| `incompatible` | Catalog metadata/schema or guidance JSON is invalid or out of bounds. |
| `unavailable` | Catalog storage or local guidance could not be read. |

Embedding affects preparation only: MCP lookups never load an embedder. The MCP server requires a successfully published active index; guidance can be read independently of that index.

## Bulk homologation (MINSA to own products)

`homologar.py` proposes, for every MINSA row, the best own product from the active catalog and writes `salida/homologacion.csv` (git-ignored, UTF-8 with BOM so Excel opens it). It reads the stored vectors directly from LanceDB: no embedder, no MCP call, no `.env`.

```sh
uv run python homologar.py            # all MINSA rows (about 15 minutes for 23005 rows)
uv run python homologar.py --limit 200   # sample the first 200 rows
```

Columns: `CodigoMed`, `NombreMed`, `Coditem`, `Item`, `Agrupador`, `tier`, `distance` (L2, non-suture rows only), `score`, `alt_2`, `alt_3` (next candidates, `Coditem`), `marca`, `CodSut`, `diferencias` (suture rows only, e.g. `long_aguja:15!=20mm; variante:-!=antibacterial`, written MINSA!=own item, `?` = not stated or not known). The summary printed at the end counts rows per tier.

Suture rows (`NombreMed` starting with `SUTURA` and a recognized material) do not use vector search. They are matched on the structured `CodSut` of the own SUTUMED (`SD`) and CIRUGIA PERUANA PLUS (`CQ`) suture items, read from `items/items.csv` and decoded with `items/codsut_estructura.json` (regenerate it from the Unilene workbook with `uv run --with openpyxl python convertir_estructura.py`). Candidates share the material family and calibre of the MINSA name; they are ranked by needle curvature, needle point, variant (antibacterial, color, barbed...), double needle, and then the nearest needle and thread length. An attribute missing from the MINSA name is unknown, not a mismatch.

| Tier | Meaning |
|---|---|
| `exacto` | Suture: material family and variant, calibre, curvature, point, needle count, needle length and thread length all stated and equal. |
| `probable` | Suture: material family, calibre, curvature and point equal; variant, lengths or needle count differ or are not stated (see `diferencias`). |
| `revisar` | Suture: same family and calibre but another curvature or point, or curvature, point or calibre not stated. Non-suture: number+unit tokens (`10 MM`, `2.5 ML`, `5 FR`, `N 12`, `TALLA S`, `5/16 IN`; inches are never converted to mm) agree with the candidate and its first meaningful word (`CATETER`, `HOJA`, `APOSITO`...) appears in it; names without numbers must share at least two words, and contrastive qualifiers (single/double/triple lumen, sterile/non-sterile, powdered/powder-free, rebreathing/non-rebreathing) must not differ; L2 distance at most 0.35 (0.45 for names that carry numbers or sizes). |
| `sin_equivalente` | Suture: no SD/CQ item with that family and calibre. Non-suture: nothing within the distance limit, or the numbers disagree. `Coditem`, `Item` and `Agrupador` are empty. |

Non-suture rows keep the vector strategy: the top 30 candidates among the non-suture own items (sutures are 96% of the catalog and would crowd them out), re-ranked by number+unit agreement, then distance (`src/homologador/generico.py`; thresholds measured on the catalog, see the comment there). Tiers are candidates for human review, not clinical equivalence; `exacto` does not compare sterility class, box size or brand variants beyond the listed attributes.

## SIGA codes (best match per MINSA row)

The 1085 homologated rows (every non-`sin_equivalente` row plus all suture rows) were searched in the SIGA catalog (CBSO search box); the raw results are kept, git-ignored, in `salida/` (`queries.json`, `siga_raw.json` for the first pass, `siga_raw2.json` for the search variants). SIGA lists results by code, not by relevance, and words its descriptions differently (NAILON for NYLON, `C/DOBLE AGUJA` for `C/2A`), so the best option is chosen by attributes (`src/homologador/siga.py`), never by position.

```sh
uv run --with openpyxl python siga_excel.py   # writes salida/homologacion_siga_final.xlsx
```

`openpyxl` is used only by that script and is not a project dependency, hence `--with`. The matching code in `siga.py` needs nothing beyond the project's own packages and is covered by the normal unit tests (the Excel writer test is skipped when openpyxl is absent).

The sheet `homologacion_siga` has the 13 columns of `homologacion.csv` plus `SIGA_estado`, `SIGA_puntaje` (0-100; 100 only for equal text), `SIGA_codigo_1`, `SIGA_descripcion_1`, `SIGA_diferencias` (MINSA!=SIGA per attribute for the main option, `?` = not stated), `SIGA_codigo_2` to `SIGA_codigo_5` (next best options), `SIGA_alternativas` (`code: description | ...` for options 2 to 5) and `SIGA_total_opciones` (all distinct codes found).

| `SIGA_estado` | Meaning |
|---|---|
| `exacto` | One option whose normalized description equals the MINSA one (accents, case, `Nº`/`N°`/`NO`, inch marks, parenthesized notes and a trailing `UNIDAD` are ignored). |
| `mejor_coincidencia` | The top option agrees on every core attribute (suture: material family, calibre, curvature, point, single/double needle and color/construction; other products: same numbers and units, head word, qualifiers, at least 75% of the MINSA words) and is strictly better than the rest; nearest needle and thread lengths win, differences are listed. |
| `aproximado` | The best option differs, or lacks, a core attribute (another calibre, point, double vs single needle, other words...). Never a different material or calibre without this estado. Review before use. |
| `ambiguo` | Two or more options tied at the top (for example the same text under two codes, or the MINSA name does not state the thread length); all are listed. |
| `sin_resultado` | SIGA returned nothing for any search variant. |

Scores and estados are candidates for human review, not clinical equivalence.
