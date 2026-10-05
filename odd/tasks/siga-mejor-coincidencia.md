# SIGA best-match selection and final Excel

Objective: for each of the 1085 homologated MINSA rows (non-`sin_equivalente` plus all suture rows) choose the best SIGA catalog code among the options captured from the CBSO search box, and write the final Excel with every extra option in additional columns.

Inputs (git-ignored, in `salida/`): `homologacion.csv` (MINSA rows and tiers), `queries.json` (row order -> cleaned query), `siga_raw.json` (first pass: one record per unique query `{q, status, rows:[[code, description]]}`), `siga_raw2.json` (second pass: `{q, v, status, total, rows}` for the 184 queries without an exact match, one record per search variant: synonym-normalized text, text without the size tail, material+calibre prefix, and a `DE` toggle; up to 3 pages of 100 rows per search).

Why: pass 1 left 897 exact matches, 27 single non-exact, 31 multiple and 130 without result. The SIGA description is usually the MINSA description with different wording (NYLON/NAILON, C/2A vs C/DOBLE AGUJA, N° removed, CC/CR abbreviations), so the best option must be chosen by attributes, not by position (SIGA lists results by code, not by relevance).

Scope: `src/homologador/siga.py` (candidate union, scoring, estado), `siga_excel.py` at repo root (builds the xlsx; `openpyxl` only through `uv run --with openpyxl`, no project dependency), tests with a small committed fixture, README section. Not in scope: more scraping, changing the homologation tiers.

Rules: suture rows reuse `atributos.parse` (material, calibre, curvature, point, mm, cm, double needle) on both texts; non-suture rows reuse the head-word/qualifier and number-unit logic of `generico.py`. Normalized-equal description = `exacto`. Choose the best candidate with all core attributes equal (material family, calibre, curvature, point, single/double needle) and the nearest needle and thread lengths = `mejor_coincidencia`, with the differences listed. Core attribute differences = `aproximado`. Two or more candidates tied at the top = `ambiguo` (all listed). None = `sin_resultado`. Never pick a different material, calibre or single/double needle as the main code without marking `aproximado`.

Output columns (in addition to the tier columns): `SIGA_estado`, `SIGA_puntaje`, `SIGA_codigo_1`, `SIGA_descripcion_1`, `SIGA_diferencias`, `SIGA_codigo_2..5` (next best options, ranked), `SIGA_alternativas` (`code: description | ...` for the options shown), `SIGA_total_opciones`.

## Tasks
- [ ] G1 — `siga.py` candidate union and scoring (suture and non-suture) with tests. Route: delegated writer.
- [ ] G2 — `siga_excel.py`, README, run on the real files and report counts and samples per estado. Route: delegated writer.
- [ ] G3 — Parent spot check (30 rows per estado) and record evidence. Route: parent.

## Evidence and limitations
(pending)
