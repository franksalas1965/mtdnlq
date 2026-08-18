# Referencia del volcado mtd10

El archivo **`mtd10.sql`** en esta carpeta es un volcado de referencia de la base de datos
**mtd10** (Mapa Topográfico Digital escala **1:10 000**).

> El prefijo **`10_`** en los nombres de esquema indica la escala 1:10 000.
> Para 1:25 000 el prefijo sería `25_`, para 1:100 000 sería `100_`, etc.
> Ver [CONVENCION_ESCALAS.md](../CONVENCION_ESCALAS.md).

## Uso del archivo

| Acción | Comando |
|--------|---------|
| Restaurar en PostgreSQL local | `pg_restore -h localhost -p 5433 -U postgres -d mtd10 --clean mtd10.sql` |
| Listar contenido sin restaurar | `pg_restore -l mtd10.sql` |
| Convertir a SQL plano | `pg_restore -f mtd10_plain.sql mtd10.sql` |

> En Windows, los binarios de PostgreSQL (`pg_restore`) suelen estar en la carpeta de
> instalación de PostgreSQL o accesibles desde WSL.

## Relación con MTD-NLQ

MTD-NLQ **no importa** este archivo al arrancar: se conecta a la BD `mtd10` que ya
tengas cargada en PostgreSQL (puerto 5433 en tu entorno).

La estructura documentada en [ESQUEMA_MTD10.md](../ESQUEMA_MTD10.md) se extrajo de este volcado.

## Origen

- Base de datos: `mtd10`
- Comentario en BD: *De Yunaisi Enero 2026*
- SRID de geometrías: **EPSG:4267** (NAD27)
- Total: **11 esquemas**, **138 tablas** temáticas y de configuración
