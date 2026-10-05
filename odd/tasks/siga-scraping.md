# SIGA codes for homologated MINSA items (Playwright MCP)

Objective: add the SIGA catalog code(s) to every homologated MINSA row (all non-`sin_equivalente` rows plus all suture rows, 1085 rows), searching each MINSA description in the official CBSO catalog search box. Two or more results go in extra columns.

Source: https://app-siafrp.mef.gob.pe/webcbso/ (MEF SIAF-RP, "Catálogo de Bienes, Servicios y Obras del SIGA MEF"). `https://catalogo.herramientasdeconsulta.com/` was not usable (its JS/CSS assets answered 401). The official page shows a "Verificar acceso" button (invisible reCAPTCHA); the user asked to click it. It passed with no visible challenge.

Method (reproducible, no project code): Playwright MCP, one browser page; for each of the 1069 unique queries the page's search box is filled and submitted and the first results page (max 25 rows, columns CÓDIGO and DESCRIPCIÓN) is read; about 1 request per 1.1 s. Queries are the MINSA name cleaned of control characters and a trailing `UNIDAD`. Results were accumulated in `window.__siga` and saved to `salida/siga_raw.json`. Direct calls to the API (`api-siafrp.mef.gob.pe`) answer 401 without the app's token, so they were not used; only the UI was driven.

Findings:
- The access token expired mid-run (about 6 minutes in): 18 queries got HTTP 401 once and recovered; the batch code then waited 4 s and retried on any non-200. All 19 failed queries were rerun successfully.
- The MINSA description usually equals the SIGA description (MINSA is the origin), so exact text matches resolve most rows; the SIGA code is 12 digits (e.g. `495700330005`), different from the MINSA `CodigoMed`.

Result (`salida/homologacion_siga.xlsx`, git-ignored, 1085 rows, extra columns `SIGA_estado`, `SIGA_total`, `SIGA_codigo_1`, `SIGA_descripcion_1`, `SIGA_codigo_2..10`, `SIGA_alternativas`):
- `exacto` 897 (a result whose normalized description equals the query; listed first), `unico` 27 (one result, different text), `multiple` 31 (several, none exact), `sin_resultado` 130.
- 303 rows have 2 or more codes. Only `exacto` is reliable; for `unico` and `multiple` the first code is not necessarily the right product (e.g. a 2x1 cm collagen sponge listed a 3x4 cm one first).

Limitations: first page only (25 rows; 7 queries had more); the 130 `sin_resultado` mostly differ in wording from SIGA (`NO`/`Nº`/`N°`, `C/2A` vs `C/DOBLE AGUJA`, trailing words); a fallback with shortened queries was not run.
