"""Apply the validated edits of estado_homologacion_items.xlsx to items/dim_homologados_minsa.xlsx.

Items sheet is the source of truth per SKU (MINSA codes, SIGA, agrupador); Detalle sheet gives the NEWCOMERCIAL columns per pair.
Non-destructive: it adds pairs and completes values, it never deletes rows.
"""
import collections
import warnings

import openpyxl

warnings.simplefilter("ignore")


def t(v):
    return "" if v is None else str(v).strip()


wb = openpyxl.load_workbook("salida/estado_homologacion_items.xlsx", data_only=True)
ws = wb["Items"]
h = [c.value for c in ws[6]]
X = {t(r[0]): dict(zip(h, r)) for r in ws.iter_rows(min_row=7, values_only=True) if r[0]}
d = wb["Detalle_MINSA_SIGA"]
hd = [c.value for c in d[3]]
D = {(t(r[0]), t(r[2])): dict(zip(hd, r)) for r in d.iter_rows(min_row=4, values_only=True) if r[0]}

dw = openpyxl.load_workbook("items/dim_homologados_minsa.xlsx")
w = dw.active
H = [c.value for c in w[1]]
ix = {c: i + 1 for i, c in enumerate(H)}


def g(r, c):
    return t(w.cell(r, ix[c]).value)


rows = {(g(r, "ID_SKU_EXTERNO"), g(r, "ID_SKU_UNILENE")): r for r in range(2, w.max_row + 1)}
log = collections.Counter()

NC = ("AGRUPADOR_NEWCOMERCIAL", "SUB_AGRUPADOR_NEWCOMERCIAL", "LINEA_NEWCOMERCIAL")
for k, r in rows.items():
    dd = D.get(k)
    if dd:
        for c in NC:
            if t(dd[c]) != g(r, c):
                w.cell(r, ix[c]).value = t(dd[c]) or None
                log["NEWCOMERCIAL celdas"] += 1

desc = {g(r, "ID_SKU_EXTERNO"): g(r, "DESC_PRODUCTO_EXTERNO") for r in rows.values()}
for k, x in X.items():
    if t(x["HOMOLOGADO"]) != "SI":
        continue
    for c in [c for c in t(x["CODIGOS_MINSA"]).split(" | ") if c]:
        if (c, k) in rows:
            continue
        siga = t(x["CODIGOS_SIGA"]).split(" | ")[0]
        n = w.max_row + 1
        vals = {
            "ID_SKU_EXTERNO": int(c) if c.isdigit() and not c.startswith("0") else c,
            "DESC_PRODUCTO_EXTERNO": desc.get(c) or t(x["DESC_MINSA"]).split("  (+")[0],
            "FUENTE": "MINSA",
            "ID_SKU_UNICO_UNILENE": k,
            "ID_SKU_UNILENE": k,
            "AGRUPADOR": t(x["AGRUPADOR"]),
            "SUBAGRUPADOR": t(x["SUBAGRUPADOR"]),
            "CodigoSIGA": siga or None,
            "VALIDACION": "OK",
        }
        for col, v in vals.items():
            w.cell(n, ix[col]).value = v
        rows[(c, k)] = n
        log["pares nuevos"] += 1
        print("NUEVO", c, k, siga, vals["DESC_PRODUCTO_EXTERNO"][:50])

# SIGA edited in Items: only for SKUs with a single MINSA code whose SIGA set differs from the dim (no guessing for multi-code SKUs)
sku_siga = collections.defaultdict(set)
for (c, k), r in rows.items():
    if g(r, "CodigoSIGA"):
        sku_siga[k].add(g(r, "CodigoSIGA"))
for (c, k), r in rows.items():
    x = X.get(k)
    if not x or not t(x["CODIGOS_SIGA"]) or g(r, "CodigoSIGA") or int(x["CANT_MINSA"] or 0) != 1:
        continue
    s = t(x["CODIGOS_SIGA"]).split(" | ")[0]
    if {s} != sku_siga[k]:
        w.cell(r, ix["CodigoSIGA"]).value = s
        log["CodigoSIGA completado"] += 1
        print("SIGA", c, k, s)

dw.save("items/dim_homologados_minsa.xlsx")
print(dict(log), "filas", w.max_row - 1)
