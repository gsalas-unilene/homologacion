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
