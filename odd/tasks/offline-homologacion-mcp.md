# Offline homologation MCP

Objective: prepare vectors for the internal catalog (`items/items.csv`) and external MINSA items (`items/items_minsa.csv`) under explicit supervision, then expose read-only candidate retrieval through MCP backed only by LanceDB.

Problem: the initial builder indexed five examples and the MCP embedded raw queries online. Online embedding is prohibited.

Scope: preserve external `CodigoMed` as text and `NombreMed`; return internal `Coditem`, `Item`, `SubFamilia`, `Agrupador` as reviewable candidates. Use `OLLAMA_HOST` and `OLLAMA_MODEL=qwen3-embedding:latest` only in supervised preparer. Agent tools must never inspect, print or source real `.env`; user explicitly authorizes only preparer Python to load those two values at invocation time; MCP must not load `.env`. `.env.example` is user-permitted but tool-blocked. No online MCP embedding or fallback; JSON is bounded review data.

Constraints: all project files were initially untracked; no git add/commit/push. Branch: `feat/offline-homologacion-mcp`. TDD strict disabled for T1–T5 by explicit user choices; ordinary functional checks, no RED/GREEN claims. RDD on; assessment unassessable because files untracked, so use independent verifier. No live indexing before bounded-memory and resource checks. Delivery strategy: ask-on-risk before any commit/PR; forecast exceeds ~400 authored lines.

## Tasks
- [x] T1 — Offline catalog and MINSA ingestion. CSV validation, codes as strings, missing MINSA name excluded with warning, generation-specific tables/atomic active manifest; mock tests and temporary DB. 22668 internal/23005 valid MINSA rows.
- [x] T2 — Read-only MCP for prepared MINSA IDs and internal vector candidates; FastMCP guard before import, real in-process client and stdio tool listing verified, no Ollama calls.
- [x] T3 — README and bounded local `homologacion_guia.json` read-only guidance MCP tool, not automatic equivalence. Three tools listed over stdio.
- [x] T4 — Invocation-time preparer-only dotenv loading with process-env precedence and exact model validation. 15 focused and 22 full guarded tests passed; verifier confirmed all tests use synthetic `config.fixture`, no real `.env` read in tests and no import-time dotenv read. `python-dotenv` declared and `uv.lock` updated offline.
- [x] T5 — Stream bounded embedding batches (`EMBEDDING_BATCH_SIZE=64`) into generation-suffixed LanceDB tables; old active manifest preserved until both tables complete. Evidence (resumed after Codex crash): 23/23 guarded tests pass (two stale `_publish_tables` test calls fixed to the batches+counts signature); temporary real LanceDB write of 64+5 internal and 3 MINSA rows matched manifest counts; incomplete-count failure left the manifest unchanged. Independent verifier not yet run.
- [ ] T6 — SUPERSEDED by F4 in `fastembed-local-embeddings.md` (Ollama host down; FastEmbed replaces it). Original text: User-authorized conditional supervised runtime sample embedding and bulk index if safe. Validate model/dimension/latency, memory/disk, active manifest row counts and one MCP lookup; no printing secrets or agent read of `.env`. Route: bounded supervised operation.

## Evidence and limitations
- Independent T1 checks validated temporary LanceDB publication and CSV counts. T2 guarded FastMCP 4.0.10 listed tools without observed PyPI GET. Previous unguarded FastMCP imports may have implicitly read `.env`; contents were never inspected/disclosed. Server now forces `FASTMCP_ENV_FILE=os.devnull` and `FASTMCP_CHECK_FOR_UPDATES=off` before third-party imports; all agent-side tests retain guards.
- Preflight before T4 found inherited OLLAMA_HOST/MODEL absent, 3.5 GiB available RAM and 934G free disk. No real Ollama call or production indexing yet. User authorized preparer-only runtime read of `.env` and conditional indexing, but streaming and sample preflight are required first.
- No source commit/push/delivery. `qwen3-embedding:latest` is mutable; weights are not pinned; directory fsync is not implemented. `.env.example` remains tool-blocked despite user authorization.

Next: optional independent T5 verification, then T6 supervised preflight and conditional index (RAM is limited: 3.5 GiB available, so confirm bounded memory first). Do not use agent tools to read real `.env` or disclose its contents.
