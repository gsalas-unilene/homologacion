# Suture homologation using the Unilene CodSut structure (brands SD and CQ only)

Objective: for MINSA rows that are sutures, homologate only against own suture items of brands SUTUMED (`SD`) and CIRUGIA PERUANA PLUS (`CQ`), matching on the structured CodSut attributes instead of vector search plus text regexes. Non-suture rows are unchanged.

Why (evidence):
- `items/unilene_codsut_estructura.xlsx` (added by the user) is the dictionary of the `CodSut` code: Marca(2) Hebra(2) Calibre(3) Aguja(2) LongAguja(3) LongHebra(3) Caja(2) Clase(1) CampoVariable(3) = 21 chars, e.g. `CPAP010TC35007024ASCE` = CP / AP / 010 / TC / 350 / 070 / 24 / A / SCE. Dictionaries: 42 marcas, 49 hebras (material variants such as antibacterial, incoloro, barbed), 29 calibres, 65 agujas (curvature + point type), 151 long-aguja, 158 long-hebra, 9 cajas, 5 clases.
- Own suture items: 21832; brand counts VS 7657, SD 7223, VE 1687, SX 1420, CP 1004, CQ 776, ... SD+CQ = 7999 items. The current run matched mostly SD but also VE, HE, BM, CP, MT, CG candidates, which the user does not want.
- Positional parsing of CodSut mostly validates against the dictionaries (a minority has unknown codes: hebra 156, caja 25, clase 16, calibre 11 items), so a text fallback is still needed.
- Current limits: vector top-30 ceiling for suture rows, numbers imprecise, no brand rule, no explicit list of differences for the reviewer.

Scope: dictionary conversion, CodSut parser, structured matching for suture rows, richer MINSA suture text parser built from the dictionaries, CSV columns, tests, README. Not in scope: non-suture rows, MCP tools, reindexing, push or PR.

Constraints: no new runtime dependency (openpyxl only through `uv run --with openpyxl` in the converter script); no embedder; agent tools never read the real `.env`; candidates are for human review, not clinical validation; conventional commits, no AI attribution; strict TDD (session config), runner `FASTMCP_ENV_FILE=NUL uv run python -m unittest discover -s tests`.

Tier rules (suture rows, own candidates restricted to marca SD and CQ):
- `exacto`: material family and variant, calibre, needle curvature, needle point, needle length, thread length and class all equal.
- `probable`: material family, calibre, needle curvature and needle point equal; lengths and/or variant differ (the nearest lengths are chosen).
- `revisar`: material family and calibre equal but curvature or point differ, or an attribute is not stated in the MINSA name.
- `sin_equivalente`: no SD/CQ item with the same material family and calibre.
- An attribute missing in the MINSA name is unknown, not a mismatch.
New CSV columns: `marca`, `CodSut`, `diferencias` (e.g. `long_aguja:15!=35mm; variante:antibacterial`).

## Tasks
- [ ] S1 — `convertir_estructura.py` converts the xlsx to `items/codsut_estructura.json` (runtime reads JSON only). Route: delegated writer.
- [ ] S2 — `src/homologador/codsut.py`: parse a CodSut into attributes using the dictionaries, graceful on unknown codes. Route: delegated writer.
- [ ] S3 — Structured suture matching, brand filter, tiers, new columns, README. Route: delegated writer.
- [ ] S4 — Extend the MINSA suture text parser from the dictionaries; measure unparsed rows and tier counts before/after. Route: delegated writer.
- [ ] S5 — Supervised full run, spot check 30 rows per tier, record counts. Route: parent.

## Evidence and limitations
(pending)
