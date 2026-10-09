# DIM_HOMOLOGADOS v2 – Homologación MINSA ↔ Unilene

Nuevo modelo depurado de la homologación de productos MINSA con SKU de Unilene, con códigos SIGA,
estado de validación y trazabilidad. Scripts compatibles con **SQL Server 2012**.

## Contenido de la carpeta

| Archivo | Qué es |
|---|---|
| `dim_homologados_minsa_v2.xlsx` | Modelo completo: RESUMEN, LEEME, DIM_HOMOLOGADOS, DIM_PRODUCTO_EXTERNO, HOMOLOGACION_REVISION, DEPURADOS |
| `sql/01_crear_objetos.sql` | Respaldo de la tabla anterior + creación de tablas, índices y restricciones + migración de otras fuentes |
| `sql/08_cargar_stg_items.sql` | Carga del maestro de items (items.csv) a `STG_ITEMS` |
| `sql/02_cargar_dim_producto_externo.sql` | Productos MINSA (descripción oficial, canónico, CodigoSIGA) |
| `sql/03_cargar_dim_homologados.sql` | Homologación depurada |
| `sql/04_cargar_homologacion_revision.sql` | Candidatos pendientes de validar |
| `sql/05_vistas.sql` | `VW_DIM_HOMOLOGADOS`, `VW_HOMOLOGACION_RESUELTA`, `VW_HOMOLOGACION_PENDIENTE` |
| `sql/06_procedimientos.sql` | `usp_HOMOLOGACION_APROBAR_REVISION`, `usp_HOMOLOGACION_COMPLETAR_FAMILIAS` |
| `sql/07_validaciones.sql` | Controles de calidad (deben devolver 0 filas) |
| `scripts/generar_dim_homologados.py` | Regenera el Excel y los scripts de datos (02, 03, 04, 08) |

## Orden de ejecución

1. `01_crear_objetos.sql` – renombra la tabla actual a `DIM_HOMOLOGADOS_BK_20261006` (no se borra nada) y crea el modelo nuevo.
   Las filas de fuentes distintas a MINSA se migran automáticamente.
2. `08_cargar_stg_items.sql`
3. `02_cargar_dim_producto_externo.sql`
4. `03_cargar_dim_homologados.sql`
5. `04_cargar_homologacion_revision.sql`
6. `05_vistas.sql`
7. `06_procedimientos.sql`
8. `07_validaciones.sql` – revisar que los controles 1 a 6 devuelvan 0.

Los scripts 02, 03, 04 y 08 son re-ejecutables (borran y recargan solo los datos MINSA).

## Modelo

```
DIM_PRODUCTO_EXTERNO (FUENTE, ID_SKU_EXTERNO)            1 fila por producto MINSA
   ├─ ID_SKU_EXTERNO_CANONICO  → resuelve códigos duplicados
   ├─ CodigoSIGA / VALIDACION_SIGA (OK, REVISION, SIN_DATO)
   └─< DIM_HOMOLOGADOS (FUENTE, ID_SKU_EXTERNO, ID_SKU_UNILENE)  UNIQUE
          VALIDACION (OK, REVISION, RECHAZADO), NIVEL, ORIGEN, auditoría
HOMOLOGACION_REVISION  candidatos con DECISION (SI/NO) → usp_HOMOLOGACION_APROBAR_REVISION
STG_ITEMS              maestro Unilene para reglas de familia y validaciones
```

- Reportes/SSIS que leían `dbo.DIM_HOMOLOGADOS` con las columnas antiguas → usar **`dbo.VW_DIM_HOMOLOGADOS`** (mismo formato + CodigoSIGA + VALIDACION).
- Tablas de hechos MINSA (ventas, compras, SIGA) → unir por **`dbo.VW_HOMOLOGACION_RESUELTA`**, que acepta cualquier código, incluso los duplicados.

## Reglas aplicadas

1. **ID_SKU_UNICO_UNILENE** (suturas) = CodSut posiciones 3-15 + `B` si es doble aguja (posición 18 = `B`). Otros agrupadores = Coditem.
2. **Familia homologable** = Coditem con el mismo ID único y marca **SD o CQ**.
3. AGRUPADOR, SUBAGRUPADOR y DPRO_DESC_SUB_FAMILIA se toman del maestro de items.
4. DESC_PRODUCTO_EXTERNO = descripción oficial del catálogo MINSA.
5. **Códigos MINSA duplicados** (mismo producto, mismo código SIGA y mismos SKU): se conserva uno canónico
   (en catálogo > sin `*` > SIGA exacto > código menor). Los demás quedan solo en DIM_PRODUCTO_EXTERNO apuntando al canónico.
6. **CodigoSIGA** solo cuando la búsqueda SIGA fue exacta; si no, queda en `CodigoSIGA_SUGERIDO` con VALIDACION_SIGA = REVISION.
7. **Depuración** (hoja DEPURADOS): SKU inexistentes en el maestro, inconsistencias de doble aguja no vendidas,
   medida distinta y códigos duplicados. Las inconsistencias de doble aguja depuradas se dejan como candidatos en HOMOLOGACION_REVISION.
   Si el SKU se vende a MINSA no se borra: queda con VALIDACION = REVISION.

## Flujo de mantenimiento

1. Revisar `VW_HOMOLOGACION_PENDIENTE` (primero lo vendido) y marcar `DECISION = 'SI'/'NO'`.
2. `EXEC dbo.usp_HOMOLOGACION_APROBAR_REVISION;` (vista previa) → `@Aplicar = 1`.
3. Al crear SKU nuevos SD/CQ: recargar `STG_ITEMS` y ejecutar `dbo.usp_HOMOLOGACION_COMPLETAR_FAMILIAS @Aplicar = 1`.
4. Ejecutar `07_validaciones.sql` después de cada cambio.

## Recomendaciones pendientes

- Cargar `STG_ITEMS` directamente desde el ERP (job SQL Agent) en lugar de items.csv.
- 65 SKU `DMNST` vendidos a MINSA no existen en items.csv: incorporarlos al maestro.
- 98 productos MINSA sin búsqueda SIGA (mangas, máscaras, mallas): ejecutar el buscador SIGA para ellos.
- 16 códigos MINSA ya no figuran en el catálogo vigente (`EN_CATALOGO_MINSA = 0`): confirmar si siguen activos.
