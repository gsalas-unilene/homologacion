/* Remove brand VE (CodSut starts with 'VE') from dbo.DIM_HOMOLOGADOS (current table). SQL Server 2012.
   The 5 SKUs below are the VE rows present in items/dim_homologados_minsa.xlsx (checked against items.csv CodSut).
   Step 1 previews; step 2 deletes inside a transaction that ends in ROLLBACK: change it to COMMIT once the count is 5. */
SET NOCOUNT ON;
GO

/* 1) Preview */
SELECT * FROM dbo.DIM_HOMOLOGADOS
WHERE ID_SKU_UNILENE IN ('PSVNA00052', 'PSVAP00357', 'PSVAP00067', 'PSVAP00478', 'PSVAP00415');
GO

/* 2) Delete */
BEGIN TRANSACTION;

DELETE FROM dbo.DIM_HOMOLOGADOS
WHERE ID_SKU_UNILENE IN ('PSVNA00052', 'PSVAP00357', 'PSVAP00067', 'PSVAP00478', 'PSVAP00415');
PRINT CAST(@@ROWCOUNT AS VARCHAR(10)) + ' filas eliminadas (esperado: 5)';

-- ROLLBACK TRANSACTION;
   COMMIT TRANSACTION --once the count matches
GO

/* 3) Check: must return 0 rows after COMMIT */
SELECT * FROM dbo.DIM_HOMOLOGADOS
WHERE ID_SKU_UNILENE IN ('PSVNA00052', 'PSVAP00357', 'PSVAP00067', 'PSVAP00478', 'PSVAP00415');
GO

/* 4) MINSA sales fact table (name not in this repo): exclude the same SKUs, e.g.
      DELETE FROM <tabla_ventas_minsa> WHERE <columna_coditem> IN ('PSVNA00052','PSVAP00357','PSVAP00067','PSVAP00478','PSVAP00415');
   If the sales table has other VE SKUs not in the dim (20 sold VE SKUs in items_vendidos_minsa.xlsx), filter them
   by CodSut LIKE 'VE%' using the item master table. */
