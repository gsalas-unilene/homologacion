"""Carga a DIM_HOMOLOGADOS los SKU de 1C con CODIGO_MINSA_ELEGIDO y busca su código SIGA.

Ejecutar desde la raíz:  python scripts/aplicar_1c_siga.py
SIGA (sin conexión): 1) el que ya tiene el código en el dim, 2) homologacion_siga_final (exacto),
3) catálogo SIGA local = todas las respuestas guardadas (siga_raw, siga_raw2, siga_raw3, buscar_siga_result)
evaluado con homologador.siga.elegir. Exacto -> se asigna; mejor_coincidencia/aproximado -> sugerido (manual);
sin opciones -> queda para buscar en SIGA (se genera salida/siga4_chunk.js para el buscador).
Salidas: items/dim_homologados_minsa.xlsx, salida/recarga_minsa_dim_homologados.sql,
         salida/vendidos_1C_mapeo_siga.xlsx, salida/siga4_chunk.js, validacion_manual_homologacion.xlsx (1C)
"""
import csv
import datetime
import io
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path('.')
sys.path.insert(0, str(ROOT / 'src'))
from homologador.siga import clave, elegir  # noqa: E402

HOY = datetime.date.today()
VAL = ROOT / 'salida/validacion_manual_homologacion.xlsx'
DIM = ROOT / 'items/dim_homologados_minsa.xlsx'
BK = ROOT / f'items/backup/dim_homologados_minsa_pre_1C_{HOY:%Y%m%d}.xlsx'
if not BK.exists():
    BK.write_bytes(DIM.read_bytes())

# ------------------------------------------------------------------ datos
it = pd.read_csv(ROOT / 'items/items.csv', dtype=str).apply(lambda c: c.str.strip())
sut = (it.Agrupador == '01. SUTURAS') & (it.CodSut.str.len() == 21)
it['UNICO'] = np.where(sut, it.CodSut.str[2:15], it.Coditem)
it['SUBAGR'] = np.where(sut, 'SUTURAS', it.SubFamilia)
I = it.set_index('Coditem')
vend = set(pd.read_excel(ROOT / 'items/items_vendidos_minsa.xlsx', header=None, dtype=str)[0].str.strip())


def leer_catalogo(path):
    lineas = []
    for raw in path.read_bytes().splitlines():
        try:
            lineas.append(raw.decode('utf-8'))
        except UnicodeDecodeError:
            lineas.append(raw.decode('cp1252', errors='replace'))
    df = pd.DataFrame(list(csv.reader(io.StringIO('\n'.join(lineas))))[1:], columns=['CodigoMed', 'NombreMed'])
    df['CodigoMed'] = df.CodigoMed.str.strip()
    df['NombreMed'] = df.NombreMed.map(lambda s: re.sub(r'[\x00-\x1f\x7f]', ' ', s).strip())
    return df.drop_duplicates('CodigoMed').set_index('CodigoMed').NombreMed


mi = leer_catalogo(ROOT / 'items/items_minsa.csv')
d = pd.read_excel(BK, dtype=str).apply(lambda c: c.str.strip())
cols = list(d.columns)
N0 = len(d)
sgf = pd.read_excel(ROOT / 'salida/homologacion_siga_final.xlsx', dtype=str).apply(lambda c: c.str.strip()).set_index('CodigoMed')

# catálogo SIGA local (todas las respuestas guardadas del buscador)
cat = {}
for f in ['siga_raw.json', 'siga_raw2.json', 'siga_raw3.json', 'siga_retry.json']:
    p = ROOT / 'salida' / f
    if p.exists():
        for e in json.load(open(p, encoding='utf-8')):
            for row in (e.get('rows') or []) if isinstance(e, dict) else []:
                if len(row) >= 2 and row[0]:
                    cat.setdefault(row[0], row[1])
p = ROOT / 'salida/buscar_siga_result.json'
if p.exists():
    for e in json.load(open(p, encoding='utf-8')):
        for o in e.get('opciones', []):
            cat.setdefault(o['codigo'], o['descripcion'])
CAT = [{'codigo': c, 'descripcion': t} for c, t in cat.items()]
print('catálogo SIGA local:', len(CAT), 'códigos')
STOP = {'DE', 'LA', 'EL', 'Y', 'CON', 'PARA', 'X', 'EN', 'SIN', 'A', 'C/A', 'N', 'NO'}


def opciones(desc):
    """Opciones del catálogo local que comparten las 2 primeras palabras significativas (como el buscador)."""
    w = [x for x in clave(desc).split() if x not in STOP and not re.match(r'^[\d/.]+$', x)][:2]
    return [o for o in CAT if all(x in clave(o['descripcion']).split() for x in w)] if w else []


# ------------------------------------------------------------------ 1C elegidos
c1 = pd.read_excel(VAL, sheet_name='1C_Vendidos_sin_MINSA', dtype=str)
c1['EXCEL_FILA'] = c1.index + 2
el = c1[c1.CODIGO_MINSA_ELEGIDO.notna()].copy()
el['CODIGO_MINSA_ELEGIDO'] = el.CODIGO_MINSA_ELEGIDO.str.strip()
validos = el[el.CODIGO_MINSA_ELEGIDO.str.fullmatch(r'\d{5}') & el.CODIGO_MINSA_ELEGIDO.isin(mi.index) & el.ID_SKU_UNILENE.isin(I.index)]
invalidos = el[~el.index.isin(validos.index)]

# SIGA por código MINSA
siga_dim = d.dropna(subset=['CodigoSIGA']).groupby('ID_SKU_EXTERNO').CodigoSIGA.first()
res = {}
for ext in sorted(set(validos.CODIGO_MINSA_ELEGIDO)):
    desc = d.loc[d.ID_SKU_EXTERNO == ext, 'DESC_PRODUCTO_EXTERNO'].iloc[0] if (d.ID_SKU_EXTERNO == ext).any() else mi[ext]
    if ext in siga_dim.index:
        res[ext] = dict(desc=desc, estado='YA EN DIM', codigo=siga_dim[ext], desc_siga=cat.get(siga_dim[ext]), fuente='dim_homologados', alt='')
        continue
    if ext in sgf.index and sgf.SIGA_estado[ext] == 'exacto':
        res[ext] = dict(desc=desc, estado='exacto', codigo=sgf.SIGA_codigo_1[ext], desc_siga=sgf.SIGA_descripcion_1[ext],
                        fuente='homologacion_siga_final', alt='')
        continue
    r = elegir(desc, opciones(desc))
    top = r['opciones'][:4]
    res[ext] = dict(desc=desc, estado=r['estado'], codigo=top[0]['codigo'] if top else None,
                    desc_siga=top[0]['descripcion'] if top else None, fuente='catálogo SIGA local' if top else '',
                    alt=' | '.join(f"{o['codigo']}: {o['descripcion']}" for o in top[1:]), dif=r['diferencias'])
R = pd.DataFrame([{'ID_SKU_EXTERNO': k, **v} for k, v in res.items()])
R['CodigoSIGA_ASIGNADO'] = np.where(R.estado.isin(['exacto', 'YA EN DIM']), R.codigo, None)
R['RESULTADO_SIGA'] = np.select([R.estado.isin(['exacto', 'YA EN DIM']), R.codigo.notna()],
                                ['CON SIGA', 'SIGA SUGERIDO (validar)'], 'SIN SIGA (buscar)')
sig = R.set_index('ID_SKU_EXTERNO')

# ------------------------------------------------------------------ nuevas filas al dim
pares = set(zip(d.ID_SKU_EXTERNO, d.ID_SKU_UNILENE))
nuevas = []
for r in validos.itertuples():
    ext, sku = r.CODIGO_MINSA_ELEGIDO, r.ID_SKU_UNILENE
    if (ext, sku) in pares:
        continue
    pares.add((ext, sku))
    x = I.loc[sku]
    nuevas.append({**{c: None for c in cols}, 'ID_SKU_EXTERNO': ext, 'DESC_PRODUCTO_EXTERNO': sig.desc[ext], 'FUENTE': 'MINSA',
                   'ID_SKU_UNICO_UNILENE': x.UNICO, 'ID_SKU_UNILENE': sku, 'AGRUPADOR': x.Agrupador, 'SUBAGRUPADOR': x.SUBAGR,
                   'CodigoSIGA': sig.CodigoSIGA_ASIGNADO[ext], 'VALIDACION': 'OK'})
N = pd.DataFrame(nuevas)
nd = pd.concat([d, N[cols]], ignore_index=True)
sg = nd.dropna(subset=['CodigoSIGA']).groupby('ID_SKU_EXTERNO').CodigoSIGA.first()
nd['CodigoSIGA'] = nd.ID_SKU_EXTERNO.map(sg)
nd = nd.sort_values(['ID_SKU_EXTERNO', 'ID_SKU_UNILENE']).reset_index(drop=True)
assert not nd.duplicated(['ID_SKU_EXTERNO', 'ID_SKU_UNILENE']).any()
wb = Workbook()
ws = wb.active
ws.title = 'sheet1'
ws.append(cols)
for r in nd[cols].itertuples(index=False):
    v = [None if x is None or (isinstance(x, float) and np.isnan(x)) else x for x in r]
    if str(v[0]).isdigit():
        v[0] = int(v[0])
    ws.append(v)
wb.save(DIM)

# ------------------------------------------------------------------ SQL recarga completa
q = lambda x: 'NULL' if x is None or (isinstance(x, float) and np.isnan(x)) or str(x).strip() == '' else "N'" + str(x).replace("'", "''") + "'"
L = ['-- DIM_HOMOLOGADOS – RECARGA COMPLETA MINSA desde items/dim_homologados_minsa.xlsx',
     f'-- Generado: {datetime.datetime.now():%Y-%m-%d %H:%M} | Filas: {len(nd)} | Códigos MINSA: {nd.ID_SKU_EXTERNO.nunique()} | Con CodigoSIGA: {nd.CodigoSIGA.notna().sum()}',
     f'-- Incluye {len(N)} filas nuevas de 1C (CODIGO_MINSA_ELEGIDO) con su CodigoSIGA cuando la búsqueda fue exacta.',
     '-- Compatible SQL Server 2012.', 'SET NOCOUNT ON;', 'SET XACT_ABORT ON;', 'GO', '',
     f"IF OBJECT_ID('dbo.DIM_HOMOLOGADOS_MINSA_BK_{HOY:%Y%m%d}_1C','U') IS NULL",
     f"    SELECT * INTO dbo.DIM_HOMOLOGADOS_MINSA_BK_{HOY:%Y%m%d}_1C FROM dbo.DIM_HOMOLOGADOS WHERE FUENTE = N'MINSA';",
     f"SELECT COUNT(*) AS filas_respaldadas FROM dbo.DIM_HOMOLOGADOS_MINSA_BK_{HOY:%Y%m%d}_1C;", 'GO', '',
     'BEGIN TRANSACTION;', '', "DELETE FROM dbo.DIM_HOMOLOGADOS WHERE FUENTE = N'MINSA';", '']
for i in range(0, len(nd), 500):
    ch = nd.iloc[i:i + 500]
    L.append(f"INSERT INTO dbo.DIM_HOMOLOGADOS ({', '.join(cols)}) VALUES")
    L.append(',\n'.join('  (' + ', '.join(q(x) for x in r) + ')' for r in ch[cols].itertuples(index=False)) + ';')
L += ['', "SELECT COUNT(*) AS filas_minsa, COUNT(DISTINCT ID_SKU_EXTERNO) AS codigos, SUM(CASE WHEN CodigoSIGA IS NOT NULL THEN 1 ELSE 0 END) AS con_siga FROM dbo.DIM_HOMOLOGADOS WHERE FUENTE = N'MINSA';",
      f'-- Esperado: {len(nd)} filas / {nd.ID_SKU_EXTERNO.nunique()} códigos / {nd.CodigoSIGA.notna().sum()} con CodigoSIGA',
      "SELECT ID_SKU_EXTERNO, ID_SKU_UNILENE, COUNT(*) c FROM dbo.DIM_HOMOLOGADOS WHERE FUENTE = N'MINSA' GROUP BY ID_SKU_EXTERNO, ID_SKU_UNILENE HAVING COUNT(*) > 1;  -- debe ser 0",
      '', '-- COMMIT TRANSACTION;', '-- ROLLBACK TRANSACTION;']
(ROOT / 'salida/recarga_minsa_dim_homologados.sql').write_text('\n'.join(L) + '\n', encoding='utf-8-sig')

# ------------------------------------------------------------------ JS para buscar los que faltan en SIGA
falt = R[R.RESULTADO_SIGA != 'CON SIGA']
items_js = []
for r in falt.itertuples():
    base = re.sub(r'\s+(UNIDAD|PAR|KIT)\s*$', '', re.sub(r'\*', '', r.desc)).strip()
    w = base.split()
    v = [base] + [' '.join(w[:k]) for k in (4, 3, 2) if len(w) > k]
    items_js.append({'q': r.desc, 'v': list(dict.fromkeys(v))})
tpl = (ROOT / 'salida/siga3_chunk.js').read_text(encoding='utf-8')
i0, i1 = tpl.index('const items = ') + len('const items = '), tpl.index('];') + 1
(ROOT / 'salida/siga4_chunk.js').write_text(tpl[:i0] + json.dumps(items_js, ensure_ascii=False) + tpl[i1:].replace('__siga3', '__siga4'), encoding='utf-8')

# ------------------------------------------------------------------ Excel de mapeo 1C
M = validos.merge(R, left_on='CODIGO_MINSA_ELEGIDO', right_on='ID_SKU_EXTERNO', how='left')
M = pd.DataFrame({'RESULTADO_SIGA': M.RESULTADO_SIGA, 'AGRUPADOR': M.AGRUPADOR, 'CODIGO_MINSA': M.CODIGO_MINSA_ELEGIDO,
                  'DESCRIPCION_MINSA': M.desc, 'CODIGO_UNILENE': M.ID_SKU_UNILENE, 'ITEM_UNILENE': M.ITEM_UNILENE,
                  'VENDIDO_MINSA': 'SI', 'CODIGO_SIGA': M.CodigoSIGA_ASIGNADO,
                  'SIGA_SUGERIDO': np.where(M.RESULTADO_SIGA == 'SIGA SUGERIDO (validar)', M.codigo, None),
                  'DESCRIPCION_SIGA': M.desc_siga, 'ESTADO_BUSQUEDA': M.estado, 'FUENTE_SIGA': M.fuente,
                  'DIFERENCIAS': M.get('dif'), 'ALTERNATIVAS_SIGA': M.alt, 'CodigoSIGA_VALIDADO': None})
M = M.sort_values(['RESULTADO_SIGA', 'AGRUPADOR', 'CODIGO_MINSA'])
INV = invalidos[['EXCEL_FILA', 'AGRUPADOR', 'ID_SKU_UNILENE', 'ITEM_UNILENE', 'CODIGO_MINSA_ELEGIDO']].assign(
    MOTIVO=lambda x: np.where(~x.CODIGO_MINSA_ELEGIDO.str.fullmatch(r'\d{5}'), 'Código no válido (revisar celda)', 'Código no existe en el catálogo MINSA'))
cnt = M.RESULTADO_SIGA.value_counts()
RES = pd.DataFrame([('SKU de 1C con código MINSA elegido', len(el)), ('  válidos', len(validos)), ('  con código no válido', len(INV)),
                    ('Filas nuevas en dim_homologados', len(N)), ('Códigos MINSA distintos', R.shape[0]),
                    ('  CON SIGA (asignado)', int((R.RESULTADO_SIGA == 'CON SIGA').sum())),
                    ('  SIGA SUGERIDO (validar)', int((R.RESULTADO_SIGA == 'SIGA SUGERIDO (validar)').sum())),
                    ('  SIN SIGA (buscar)', int((R.RESULTADO_SIGA == 'SIN SIGA (buscar)').sum())),
                    ('Filas dim antes → después', f'{N0} → {len(nd)}'),
                    ('SKU vendidos cubiertos antes → después', f"{len(set(d.ID_SKU_UNILENE) & vend)} → {len(set(nd.ID_SKU_UNILENE) & vend)} de {len(vend)}"),
                    ('Para buscar en SIGA', 'salida/siga4_chunk.js (mismo buscador que siga3)')], columns=['Concepto', 'Valor'])
HF = PatternFill('solid', fgColor='1F4E78')
COLR = {'CON SIGA': 'C6EFCE', 'SIGA SUGERIDO (validar)': 'FFF2CC', 'SIN SIGA (buscar)': 'F8CBAD'}
out = ROOT / 'salida/vendidos_1C_mapeo_siga.xlsx'
with pd.ExcelWriter(out, engine='openpyxl') as w:
    for n, df in [('Resumen', RES), ('Mapeo_1C', M), ('Con_SIGA', M[M.RESULTADO_SIGA == 'CON SIGA']),
                  ('Sin_SIGA', M[M.RESULTADO_SIGA != 'CON SIGA']), ('Codigo_no_valido', INV)]:
        df.to_excel(w, sheet_name=n, index=False)
        ws = w.sheets[n]
        for c in ws[1]:
            c.font = Font(bold=True, color='FFFFFF')
            c.fill = HF
            c.alignment = Alignment(wrap_text=True, horizontal='center', vertical='center')
        for j, cn in enumerate(df.columns, 1):
            Lm = max([len(str(cn))] + [len(str(x)) for x in df[cn].fillna('')]) if len(df) else len(str(cn))
            ws.column_dimensions[get_column_letter(j)].width = min(max(11, Lm + 2), 60)
        if n != 'Resumen':
            ws.freeze_panes = 'C2'
            ws.auto_filter.ref = f'A1:{get_column_letter(ws.max_column)}{max(ws.max_row, 2)}'
        if 'RESULTADO_SIGA' in df.columns:
            for r in range(2, ws.max_row + 1):
                ws.cell(r, 1).fill = PatternFill('solid', fgColor=COLR.get(ws.cell(r, 1).value, 'FFFFFF'))
        if 'CodigoSIGA_VALIDADO' in df.columns:
            j = list(df.columns).index('CodigoSIGA_VALIDADO') + 1
            for r in range(2, ws.max_row + 1):
                ws.cell(r, j).fill = PatternFill('solid', fgColor='FFF2CC')

# ------------------------------------------------------------------ validación: marcar 1C
wb = load_workbook(VAL)
ws = wb['1C_Vendidos_sin_MINSA']
h = [c.value for c in ws[1]]
if 'CODIGO_SIGA' not in h:
    j = ws.max_column + 1
    c = ws.cell(1, j, 'CODIGO_SIGA')
    c.font = Font(bold=True, color='FFFFFF')
    c.fill = HF
    ws.column_dimensions[get_column_letter(j)].width = 22
    h.append('CODIGO_SIGA')
js, jo = h.index('CODIGO_SIGA') + 1, h.index('OBSERVACION') + 1
okf, inv_f = set(validos.EXCEL_FILA), set(INV.EXCEL_FILA)
cod_f = dict(zip(validos.EXCEL_FILA, validos.CODIGO_MINSA_ELEGIDO))
for r in range(2, ws.max_row + 1):
    if r in okf:
        e = cod_f[r]
        ws.cell(r, jo).value = 'Cargado en DIM – ' + sig.RESULTADO_SIGA[e]
        ws.cell(r, js).value = sig.CodigoSIGA_ASIGNADO[e] or (f'sugerido {sig.codigo[e]}' if sig.codigo[e] else 'SIN SIGA')
        ws.cell(r, js).fill = PatternFill('solid', fgColor=COLR[sig.RESULTADO_SIGA[e]])
    elif r in inv_f:
        ws.cell(r, jo).value = 'Código MINSA no válido: corregir'
        ws.cell(r, jo).fill = PatternFill('solid', fgColor='F8CBAD')
ws.auto_filter.ref = f'A1:{get_column_letter(ws.max_column)}{ws.max_row}'
wb.save(VAL)
print(RES.to_string(index=False))
print(R.RESULTADO_SIGA.value_counts().to_dict())
