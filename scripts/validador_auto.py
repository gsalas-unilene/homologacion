"""Validación automática MINSA ↔ SKU Unilene para suturas, sobre homologador.atributos.

Reglas acordadas (07/10/2026):
  * Doble aguja: MINSA "C/DOBLE AGUJA" (se estandariza C/2A, C/2 A, 2C/A, C/2 AGUJAS); SKU: "C/2A" en la descripción.
  * Material, calibre, curvatura, tipo de punta, nº de agujas, color, nº de hebras: deben ser iguales.
  * Largo de hebra (cm): sin tolerancia.  Largo de aguja (mm): solo redondeo, |dif| <= 0.5 mm.
  * Variantes del SKU no mencionadas por MINSA (ANTIBACTERIAL, MICROPUNTA, CON SOPORTE...): revisión manual.
  * Calibre 1/0 = 0 (notación USP). Atributo desconocido en uno de los lados: revisión manual.
Resultado: AUTO_SI, AUTO_NO o MANUAL, con el motivo.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from homologador import atributos as A  # noqa: E402

STD = [(r'C/\s?2\s?AGUJAS?\b', 'C/DOBLE AGUJA'), (r'C/\s?2\s?A\b', 'C/DOBLE AGUJA'),
       (r'(?<![\d/])2C/A\b', 'C/DOBLE AGUJA'), (r'(?<!C/)\bDOBLE AGUJA', 'C/DOBLE AGUJA')]
VARIANTES = ['ANTIBACTERIAL', 'MICROPUNTA', 'SOPORTE', 'TRICLOSAN', 'LOOP', 'CARRETE', 'BLISTER']
COLORES = ['AZUL', 'NEGRO', 'NEGRA', 'VERDE', 'VIOLETA', 'BLANCO', 'BLANCA', 'INCOLORO', 'TRANSPARENTE']
ETIQUETAS = {'mat': 'material', 'gauge': 'calibre', 'curv': 'curvatura', 'type': 'punta', 'mm': 'mm aguja',
             'cm': 'cm hebra', 'needles': 'nº agujas', 'color': 'color', 'hebras': 'nº hebras'}


def estandarizar(desc: str) -> str:
    """Descripción MINSA con la doble aguja escrita siempre como C/DOBLE AGUJA."""
    for a, b in STD:
        desc = re.sub(a, b, desc)
    return desc


def _color(t):
    c = next((c for c in COLORES if re.search(rf'\b{c}\b', t)), None)
    return {'NEGRA': 'NEGRO', 'BLANCA': 'BLANCO', 'TRANSPARENTE': 'INCOLORO'}.get(c, c)


def _extra(attrs, t, doble):
    if attrs.get('gauge') == '1/0':          # notación USP: 1/0 = 0
        attrs['gauge'] = '0'
    attrs['needles'] = 0 if re.search(A.NO_NEEDLE, t) else (2 if doble else 1)
    attrs['color'] = _color(t)
    m = re.search(r'(\d+)\s*HEBRAS', t)
    attrs['hebras'] = m.group(1) if m else None
    return attrs


def parse_minsa(desc: str) -> dict:
    t = A.norm(estandarizar(desc))
    return _extra(A.parse(t), t, 'C/DOBLE AGUJA' in t)


def parse_sku(item: str) -> dict:
    t = A.norm(item)
    return _extra(A.parse_item(t), t, bool(re.search(r'\bC/2\s?A\b', t)))


def evaluar(desc_minsa: str, item: str, x: dict | None = None, y: dict | None = None):
    """(resultado, motivo) para un par MINSA / SKU de sutura."""
    x = x or parse_minsa(desc_minsa)
    y = y or parse_sku(item)
    tm, ti = A.norm(desc_minsa), A.norm(item)
    dif, desc = [], []
    claves = ['mat', 'gauge', 'needles', 'color', 'hebras']
    claves += ['cm'] if x['needles'] == 0 or y['needles'] == 0 else ['curv', 'type', 'mm', 'cm']
    for k in claves:
        a, b = x.get(k), y.get(k)
        if k == 'color' and (a is None or b is None):
            continue                                   # MINSA genérico sin color: no bloquea
        if k == 'hebras' and (a is None and b is None):
            continue
        if a is None or b is None:
            desc.append(ETIQUETAS[k])
            continue
        if k == 'mm':
            if abs(float(a) - float(b)) > 0.5:
                dif.append(f'mm aguja {a}≠{b}')
        elif k == 'cm':
            if float(a) != float(b):
                dif.append(f'cm hebra {a}≠{b}')
        elif a != b:
            dif.append(f'{ETIQUETAS[k]} {a}≠{b}')
    if dif:
        return 'AUTO_NO', '; '.join(dif)
    var = [v for v in VARIANTES if v in ti and v not in tm]
    if var:
        return 'MANUAL', 'variante SKU: ' + ', '.join(var)
    if desc:
        return 'MANUAL', 'sin dato: ' + ', '.join(desc)
    return 'AUTO_SI', 'atributos iguales'
