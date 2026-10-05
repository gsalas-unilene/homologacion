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
- [x] S1 — `convertir_estructura.py` converts the xlsx to `items/codsut_estructura.json` (runtime reads JSON only). Route: delegated writer.
- [x] S2 — `src/homologador/codsut.py`: parse a CodSut into attributes using the dictionaries, graceful on unknown codes. Route: delegated writer.
- [x] S3 — Structured suture matching, brand filter, tiers, new columns, README. Route: delegated writer.
- [x] S4 — Extend the MINSA suture text parser from the dictionaries; measure unparsed rows and tier counts before/after. Route: delegated writer.
- [x] S5 — Supervised full run, spot check 30 rows per tier, record counts. Route: parent.

## Evidence and limitations
- S1 (cd057b3): `convertir_estructura.py` writes `items/codsut_estructura.json` (marca 42, hebra 49, calibre 29, aguja 65, long_aguja 151, long_hebra 158, caja 9, clase 5, campo_variable 67); the xlsx and json are committed, runtime reads only the json (openpyxl only via `uv run --with openpyxl`).
- S2 (9e349d8): `src/homologador/codsut.py` `parse_codsut` decodes the 21 positions (also truncated 17-20 char codes), `atributos_item` fills unknown attributes from the Item text. Over the 7999 SD/CQ suture items the code alone leaves None: familia 73, calibre 9, curvatura 10, long_hebra 8 (punta/long_aguja None are mostly legitimate: no needle, multipack, straight needle); with the text fallback familia 56. Hebra codes not in the dictionary (63 items, e.g. FC collagen, PM polyethylene variants) get the family from the text or stay out of the index.
- S3 (cd0a0d6): `src/homologador/suturas.py` (index by (family, calibre) of SD/CQ items read from `items/items.csv`; the LanceDB items table has no CodSut) and CSV columns `marca`, `CodSut`, `diferencias`; suture rows no longer use vector search. Tiers: exacto (all stated and equal), probable (family+calibre+curvature+point equal; variant, lengths or needle count differ or are not stated), revisar (curvature or point differ or are not stated, or calibre not stated), sin_equivalente (no SD/CQ item with family+calibre). Ranking: curvature, point, variant, needle count, strands, nearest needle length, nearest thread length, SD before CQ, Coditem. Decisions: no vector tie-break (the structured ranking is deterministic and the vector add nothing once family+calibre match); sterility class is not compared (MINSA names do not state it), only single/double needle; the MINSA name cannot say sterile/non-sterile, so `exacto` does not vouch for it.
- S4: new tests first. `atributos_texto` now reads needle abbreviations (CC/CT cortante, CR redonda, `1/2CR 40MM`), dictionary needle codes with length (`MR 20`, `MC 20`, `(TC 30)`), cylindrical/conical points, DEXON, USP `1/0` = calibre `0` (own catalog has no `1/0`; before this fix 35 rows had no candidate for that reason), and ignores stray mm on multipack names. Measured on the 998 MINSA rows starting with SUTURA (unparsed material / calibre / curvature / needle point, needle rows only for the last two): before (old regex parser) 7 / 9 / 21 / 15; after 7 / 9 / 16 / 13. The first S3 draft of the new parser had 7 / 9 / 20 / 43 before the abbreviation rules. Remaining 25 rows with any unparsed attribute: 3x bare `CATGUT CROMICO`, 2x `VICRYL O DEXON` without data, 7 barbed (`CON PUAS`, no material stated; they take the generic path), 4 adhesive skin closures (no calibre), 3 double-needle 'ESPATULADA' without curvature, 2 pacemaker steel wire (`CIRCULO RECTA`), polyethylene `Nº 0/2` without curvature and 2 names without curvature (`C/A CIRCULO REDONDA 25 mm`).
- Tier counts over the 998 SUTURA rows (structured match, scratch script, not the full pipeline): exacto 717, probable 234, revisar 26, sin_equivalente 21. The 21 sin_equivalente: 7 barbed (no family; the real pipeline routes them to the generic strategy), 4 adhesive (no calibre), 10 family+calibre absent from SD/CQ (polyethylene 0 x2, polyglyconate 3/0 x2, steel 2/0 x2 and 1 each of PGLA 4, PGA 4, PGA 3, steel 2).
- Checks: `FASTMCP_ENV_FILE=NUL uv run python -m unittest discover -s tests`: 121 tests OK. `homologar.py --limit 300` could not write `salida/homologacion.csv` (PermissionError: the file is locked by another process); `homologar.homologar(Path('salida/prueba_s4.csv'), limit=1500)` ran end to end with the 13 columns: exacto 49, probable 11, revisar 6, sin_equivalente 1434 (the first 1500 MINSA rows are mostly non-suture).
- Limitations: S5 (full run, spot check) is the parent's. Variant matching is by tags from the text and from the hebra code; nylon/silk colors compare only when both sides state one. Barbed sutures cannot be matched because the MINSA name does not state the material.

## S5 full run (2026-10-05)
- 121 tests OK. Full run (23005 rows): exacto 717, probable 234, revisar 113, sin_equivalente 21941. Suture rows (998): exacto 717, probable 234, revisar 26, sin_equivalente 21; every suture match is brand SD (937) or CQ (40). Non-suture revisar unchanged (87).
- Spot check (30 exacto, 30 probable, 26 revisar, by eye): exacto rows agree with the CodSut on material, calibre, curvature, point, lengths and single/double needle. Probable rows differ in lengths (needle 1-5 mm, thread 5-25 cm) or variant wording.
- Limitations: 56 of 234 probable rows have empty `diferencias` because the MINSA name omits a length (unknown, not mismatch); some `variante` differences are only wording (`negro` vs `negro,trenzado`); sterility class is not compared; `salida/homologacion.csv` had to be closed in Excel before the CLI could overwrite it.
