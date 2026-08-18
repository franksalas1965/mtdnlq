# MTD — Convención de escalas y prefijos de esquema

En el Mapa Topográfico Digital (MTD), el **número del prefijo** de cada esquema
indica el **denominador de la escala** cartográfica.

---

## Regla general

```
Prefijo N_  →  escala 1:N 000
Base mtdN   →  base de datos de esa escala
```

| Prefijo | Escala | Base de datos | Ejemplo de esquema |
|---------|--------|---------------|-------------------|
| `10_` | **1:10 000** | `mtd10` | `10_hidrografia` |
| `25_` | **1:25 000** | `mtd25` | `25_hidrografia` |
| `50_` | **1:50 000** | `mtd50` | `50_red_vial` |
| `100_` | **1:100 000** | `mtd100` | `100_puntos_poblados` |
| `250_` | **1:250 000** | `mtd250` | `250_limites_estatales` |

El nombre temático **después del prefijo** se repite en todas las escalas:

```
{N}_hidrografia
{N}_red_vial
{N}_relieve
{N}_puntos_poblados
{N}_limites_estatales
…
```

Solo cambia el número inicial según la escala del mapa.

---

## Ejemplos

| Lo que ves en pgAdmin | Significado |
|-----------------------|-------------|
| `10_hidrografia.rios_y_arroyos_lineal` | Hidrografía a escala **1:10 000** |
| `25_hidrografia.rios_y_arroyos_lineal` | La misma capa a escala **1:25 000** |
| `100_red_vial.vias_de_comunicacion_lineal` | Red vial a escala **1:100 000** |

La columna `escala` dentro de las tablas también puede contener valores como `1:10000`.

---

## Configuración en MTD-NLQ

Cada instancia del servicio apunta a **una escala** (una base de datos):

```env
# MTD 1:10 000
POSTGRES_DB=mtd10
MTDNLQ_HOST_PORT=8001
ALLOWED_SCHEMAS=10_hidrografia,10_red_vial,10_relieve,...

# MTD 1:25 000 (segunda instancia)
POSTGRES_DB=mtd25
MTDNLQ_HOST_PORT=8002
ALLOWED_SCHEMAS=25_hidrografia,25_red_vial,25_relieve,...

# MTD 1:100 000
POSTGRES_DB=mtd100
MTDNLQ_HOST_PORT=8003
ALLOWED_SCHEMAS=100_hidrografia,100_red_vial,...
```

Para listar esquemas de una escala en PostgreSQL:

```sql
-- Escala 1:10 000
SELECT schema_name FROM information_schema.schemata
WHERE schema_name LIKE '10\_%' ESCAPE '\'
ORDER BY 1;

-- Escala 1:25 000
SELECT schema_name FROM information_schema.schemata
WHERE schema_name LIKE '25\_%' ESCAPE '\'
ORDER BY 1;
```

---

## Esquema de configuración (todas las escalas)

En cualquier escala puede existir `{N}_configuraciones` con tablas internas
del sistema (usuarios, roles). **No incluir** en `ALLOWED_SCHEMAS` para consultas NL.

---

## Referencias

- Esquema detallado escala 1:10 000: [ESQUEMA_MTD10.md](ESQUEMA_MTD10.md)
- Volcado de ejemplo: [schema/mtd10.sql](schema/mtd10.sql)
- Varias escalas en paralelo: [GUIA_USO_SERVICIO.md §7](GUIA_USO_SERVICIO.md#7-consultar-otra-escala-del-mtd)
