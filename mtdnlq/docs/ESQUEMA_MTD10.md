# MTD 1:10 000 — Esquema de la base de datos mtd10

Referencia extraída del volcado [schema/mtd10.sql](schema/mtd10.sql).

> **Convención de escalas:** el prefijo `10_` significa escala **1:10 000**.
> Para 1:25 000 sería `25_`, para 1:100 000 sería `100_`, etc.
> Ver [CONVENCION_ESCALAS.md](CONVENCION_ESCALAS.md).

---

## Resumen

| Propiedad | Valor |
|-----------|-------|
| Base de datos | `mtd10` |
| Escala | 1:10 000 |
| SRID geometrías | **4267** (NAD27) |
| Prefijo esquemas | `10_` (= escala **1:10 000**; ver [CONVENCION_ESCALAS.md](CONVENCION_ESCALAS.md)) |
| Esquemas temáticos | 10 (+ 1 de configuración del sistema) |
| Tablas totales | 138 |

### Columnas comunes en capas MTD

Casi todas las tablas geográficas comparten:

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `geo_id` | varchar | Identificador único del objeto |
| `geom` | geometry(Geometry,4267) | Geometría PostGIS |
| `geocodigo` | varchar(10) | Código temático MTD |
| `escala` | varchar(7) | Escala del objeto (ej. 1:10000) |
| `nomenclatura` | varchar(12) | Código de nomenclatura |
| `nombre` | varchar | Nombre del elemento (cuando aplica) |
| `descripcion` | varchar | Descripción |
| `fecha_creacion` | varchar | Fecha de creación |
| `fecha_actualizacion` | varchar | Última actualización |

Los sufijos de tabla indican el tipo geométrico:

| Sufijo | Geometría típica |
|--------|------------------|
| `_areal` | Polígonos (superficies) |
| `_lineal` | Líneas |
| `_puntual` | Puntos |
| `_puntual_vector` | Símbos / vectores puntuales |

---

## Esquemas temáticos

### `10_hidrografia` — 36 tablas (Geocódigo 30000000)

Hidrografía: ríos, arroyos, embalses, canales, costas, fondo marino, etc.

Tablas destacadas:

- `rios_y_arroyos_lineal`, `rios_y_arroyos_areal`
- `embalses_areal`, `embalses_lineal`, `embalses_puntual`
- `fuentes_de_agua_puntual`
- `zanjas_y_canales_lineal`, `zanjas_y_canales_secos_lineal`
- `rasgos_costeros_lineal`, `rasgos_costeros_areal`
- `diques_lineal`, `diques_areal`
- `vados_lineal`

### `10_hidrografia_presas` — 2 tablas

- `presas_areal`
- `presas_lineal`

### `10_red_vial` — 22 tablas (Geocódigo 20000000)

Red vial y ferroviaria:

- `vias_de_comunicacion_lineal`, `vias_de_comunicacion_areal`
- `caminos_y_senderos_lineal`
- `via_ferrea_lineal`
- `viaductos_y_puentes_lineal`, `viaductos_y_puentes_areal`
- `construcciones_ferroviarias_*`
- `paso_peatonal_*`
- `caracteristica_de_red_vial_lineal`

### `10_relieve` — 14 tablas (Geocódigo 20000000)

Relieve y curvas de nivel:

- `curvas_lineal`, `curvas_puntual_vector`
- `formas_de_relieve_areal`, `formas_de_relieve_lineal`
- `depresiones_y_farrallones_*`
- `barrancos_surcos_y_terrazas_*`
- `tumulos_y_otros_*`

### `10_puntos_poblados` — 7 tablas (Geocódigo 40000000)

Asentamientos humanos:

- `ciudad_puntual`, `ciudad_areal` — columnas: `nombre`, `cantidad_habitantes`, `categoria_poblacional`, `tipo_asentamiento`
- `construcciones_aisladas_*`
- `estructura_punto_poblado_areal`

### `10_limites_estatales` — 1 tabla

- `limites_estatales_lineal` — límites territoriales administrativos

### `10_provincias_y_cercas` — 2 tablas

- `limites_estatales_areal`
- `cercas_y_muros_lineal`

### `10_areas_verdes_y_terrenos` — 20 tablas (Geocódigo 70000000)

Vegetación, malezas, superficies rocosas, zonas bajas:

- `vegetacion_boscosa_areal`, `vegetacion_herbacea_areal`
- `plantaciones_lenosas_areal`
- `superficie_rocosa_areal`, `superficie_no_rocosa_areal`
- `malezas_*`, `zonas_bajas_*`

### `10_objetivos_economicos` — 28 tablas (Geocódigo 50000000)

Industria, objetivos económicos, sociales y culturales:

- `fabricas_e_industrias_*`
- `objetivos_economicos_*`
- `transporte_aereo_*`
- `iglesias_y_santuarios_*`
- `extraccion_de_minerales_*`, `minas_y_perforaciones_*`
- `depositos_agua_combustible_otros_*`

### `10_puntos_de_apoyo` — 1 tabla

- `puntos_de_apoyo_puntual` — puntos de apoyo topográfico

### `10_configuraciones` — 5 tablas (solo sistema)

Tablas de configuración del editor MTD (usuarios, roles, restricciones).
**No incluir en consultas NL de mapa** salvo que se requiera explícitamente:

- `restricciones`, `ordentematicas`, `eliminar`, `elimina_puntuales`, `simbolos_rotados`

---

## ALLOWED_SCHEMAS recomendado para MTD-NLQ

En `.env`, lista solo esquemas temáticos consultables:

```env
ALLOWED_SCHEMAS=10_areas_verdes_y_terrenos,10_hidrografia,10_hidrografia_presas,10_limites_estatales,10_objetivos_economicos,10_provincias_y_cercas,10_puntos_de_apoyo,10_puntos_poblados,10_red_vial,10_relieve
```

Omitir `10_configuraciones` evita que el LLM genere SQL sobre tablas internas del sistema.

---

## Ejemplos de preguntas alineadas con el esquema real

| Pregunta natural | Tablas involucradas |
|------------------|---------------------|
| *¿Cuántos ríos y arroyos hay?* | `10_hidrografia.rios_y_arroyos_lineal` |
| *Dame las ciudades con más de 50000 habitantes* | `10_puntos_poblados.ciudad_puntual` |
| *Muéstrame las presas* | `10_hidrografia_presas.presas_areal` |
| *Lista las vías de comunicación* | `10_red_vial.vias_de_comunicacion_lineal` |
| *Curvas de nivel del relieve* | `10_relieve.curvas_lineal` |
| *Límites estatales* | `10_limites_estatales.limites_estatales_lineal` |
| *Puntos de apoyo topográfico* | `10_puntos_de_apoyo.puntos_de_apoyo_puntual` |
| *Fábricas e industrias* | `10_objetivos_economicos.fabricas_e_industrias_puntual` |

---

## Notas para integración web / QGIS

- Las respuestas de MTD-NLQ incluyen `ST_AsGeoJSON(geom)::json AS geometry`.
- El SRID **4267** puede requerir reproyección a **EPSG:4326** o **EPSG:32617** en el cliente
  según el CRS del visor.
- Muchas entidades usan `nombre` y `descripcion` para búsquedas con `ILIKE`.

---

## Listado completo de tablas por esquema

<details>
<summary>10_areas_verdes_y_terrenos (20)</summary>

- cultivos_tecnicos_artificiales_areal
- malezas_areal, malezas_lineal, malezas_puntual, malezas_puntual_vector
- plantaciones_lenosas_areal
- simbolo_superficie_rocosa_puntual, simbolo_superficie_rocosa_puntual_vector
- superficie_no_rocosa_areal, superficie_rocosa_areal
- vegetacion_boscosa_areal, vegetacion_boscosa_lineal
- vegetacion_herbacea_areal, vegetacion_herbacea_artificial_areal
- vegetacion_herbacea_puntual, vegetacion_lineal, vegetacion_puntual, vegetacion_puntual_vector
- zonas_bajas_areal, zonas_bajas_puntual

</details>

<details>
<summary>10_hidrografia (36)</summary>

- caracteristicas_de_hidrografia_lineal, caracteristicas_de_hidrografia_puntual, caracteristicas_de_hidrografia_puntual_vector
- conductoras_lineal, conductoras_puntual
- diques_areal, diques_lineal
- elementos_corrientes_de_agua_lineal, elementos_corrientes_de_agua_puntual_vector
- embalses_areal, embalses_lineal, embalses_puntual
- fuentes_de_agua_puntual, fuentes_de_agua_puntual_vector
- isla_areal
- objetos_de_navegacion_areal, objetos_de_navegacion_lineal, objetos_de_navegacion_puntual_vector
- rasgos_costeros_areal, rasgos_costeros_lineal, rasgos_costeros_puntual
- relieve_del_fondo_marino_areal, relieve_del_fondo_marino_lineal, relieve_del_fondo_marino_puntual, relieve_del_fondo_marino_puntual_vector
- rios_y_arroyos_areal, rios_y_arroyos_lineal, rios_y_arroyos_puntual_vector
- simbolos_de_peligro_maritimo_puntual
- vados_lineal, vados_puntual, vados_puntual_vector
- zanjas_y_canales_areal, zanjas_y_canales_lineal
- zanjas_y_canales_secos_areal, zanjas_y_canales_secos_lineal

</details>

<details>
<summary>10_red_vial (22), 10_relieve (14), 10_objetivos_economicos (28)</summary>

Ver volcado `mtd10.sql` o consultar en vivo:

```sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema LIKE '10\_%' ESCAPE '\'
ORDER BY 1, 2;
```

</details>
