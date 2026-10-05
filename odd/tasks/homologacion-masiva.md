# Bulk homologation: MINSA -> own products (items.csv)

Objective: produce, for every row of `items/items_minsa.csv` (23005 rows), the best matching own product from `items/items.csv` (22668 rows), with a confidence tier, as a reviewable CSV. Suture rows use attribute re-ranking; the rest use a generic strategy.

Why: the user needs the full MINSA catalog homologated to their own products. Evidence: own catalog is 96% sutures (21832 of 22668), 836 non-suture items across 13 groups (Linea Xterie, mallas, plasticos, guantes, sondas...). MINSA is mostly screws, plates, tubes, catheters (about 1000 start with SUTURA), so most MINSA rows are expected to have no equivalent. Prototype (scratchpad, 50 sampled suture rows): exact candidate at rank 1 went from 12 to 31 of 34 when re-ranking the top-30 vector candidates by parsed attributes (material, gauge, needle curvature, needle type, mm, cm). 10 of 50 rows were not parsed (rules missing).

Scope: new module(s) under `src/homologador/`, a CLI entry (`homologar.py` at repo root, like `poblar_catalogo.py`), tests, README section. Reads the active LanceDB catalog directly (not through MCP tools). Output `salida/homologacion.csv` (git-ignored). Not in scope: changing the MCP tools, reindexing, any clinical equivalence claim, push or PR.

Constraints: no embedder at lookup (reuse stored vectors, L2); agent tools never read the real `.env`; tiers are candidates for human review, not clinical validation; conventional commits, no AI attribution (user CLAUDE.md); TDD mode: strict enabled by session config (source: user CLAUDE.md), runner `uv run python -m unittest discover -s tests` with `FASTMCP_ENV_FILE=NUL`.

Output columns: CodigoMed, NombreMed, Coditem, Item, Agrupador, tier (`exacto`, `revisar`, `sin_equivalente`), distance, score, plus alt_2 and alt_3 Coditem. Tier rules: suture rows -> `exacto` if material, gauge, curvature and needle type all equal; `revisar` if family matches but an attribute differs; non-suture rows -> `revisar` if L2 distance <= threshold and parsed numbers/units agree, else `sin_equivalente`; any row with distance > threshold -> `sin_equivalente`. Threshold chosen from the data (prototype: suture matches 0.17-0.31, an unrelated vaccine 1.05).

## Tasks
- [ ] H1 — Attribute parser for sutures (`src/homologador/atributos.py`): port the prototype, extend rules for the rows it could not parse; unit tests with real examples. Route: delegated writer.
- [ ] H2 — Generic strategy for non-suture rows: numeric/unit token agreement over top-30 vector candidates plus distance threshold. Route: delegated writer (same writer, same change).
- [ ] H3 — `homologar.py` CLI: batch run over all MINSA rows, CSV output, summary counts per tier, README section. Route: delegated writer.
- [ ] H4 — Supervised full run, spot-check 30 random rows per tier, record counts. Route: parent + bounded operation.

## Evidence and limitations
(pending)
