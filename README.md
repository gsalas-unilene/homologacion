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

Columns: `CodigoMed`, `NombreMed`, `Coditem`, `Item`, `Agrupador`, `tier`, `distance` (L2), `score`, `alt_2`, `alt_3` (next candidates, `Coditem`). The summary printed at the end counts rows per tier.

| Tier | Meaning |
|---|---|
| `exacto` | Suture whose material, gauge, needle curvature and needle type (or material, gauge and length for needle-less sutures) all equal the candidate's. Accepted at any distance. |
| `revisar` | Suture of the same material with another attribute, or a non-suture whose number+unit tokens (`10 MM`, `2.5 ML`, `5 FR`, `N 12`) agree with the candidate; in both cases L2 distance is at most 0.35. |
| `sin_equivalente` | Nothing within 0.35, or the numbers disagree. `Coditem`, `Item` and `Agrupador` are empty; `distance` is the nearest vector. |

How it works: the top 30 vector candidates are re-ranked. Sutures (`NombreMed` starting with `SUTURA`) by parsed attributes (`src/homologador/atributos.py`); the rest by number+unit agreement, then distance (`src/homologador/generico.py`). The 0.35 threshold was measured on the catalog (see the comment in `generico.py`). Tiers are candidates for human review: they are not clinical equivalence, and `exacto` does not compare brand, color or sterilization.
