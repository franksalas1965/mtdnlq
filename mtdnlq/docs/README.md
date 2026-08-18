# Documentación MTD-NLQ

**MTD-NLQ** (*Mapa Topográfico Digital — Natural Language Query*)  
Servicio FastAPI para consultar bases PostGIS del MTD en lenguaje natural.

---

## Guías de uso

| Documento | Para quién | Contenido |
|-----------|------------|-----------|
| [CONVENCION_ESCALAS.md](CONVENCION_ESCALAS.md) | **Todos** | Prefijos `10_`=1:10 000, `25_`=1:25 000, `100_`=1:100 000… |
| [GUIA_USO_SERVICIO.md](GUIA_USO_SERVICIO.md) | Empezar aquí | Instalación y configuración `mtd10` |
| [PRUEBAS_INICIALES.md](PRUEBAS_INICIALES.md) | **Tras arrancar** | Health, schema, consultas NL, pytest |
| [MEJORAR_CALIDAD_SQL.md](MEJORAR_CALIDAD_SQL.md) | **Errores 422 / SQL malo** | Comentarios en BD, modelo, preguntas, ajustes |
| [ARQUITECTURA_MULTI_ESCALA.md](ARQUITECTURA_MULTI_ESCALA.md) | Sysadmin / QGIS | Un servicio, varias escalas, cola async |
| [CONFIGURACION_LLM.md](CONFIGURACION_LLM.md) | Sysadmin | Ollama local/cloud, CPU/GPU |
| [ESQUEMA_MTD10.md](ESQUEMA_MTD10.md) | Desarrolladores | Esquema mtd10 (1:10 000): 138 tablas, columnas |
| [INTEGRACION_WEB_QGIS.md](INTEGRACION_WEB_QGIS.md) | Frontend / QGIS | API REST, proxy Next.js, plugin QGIS |
| [Plugin QGIS](../mtdnlq_qgis/README.md) | QGIS 3.40.x | Instalación, consultas NL, localizar en mapa |
| [EJECUCION_SERVICIO.md](EJECUCION_SERVICIO.md) | Operación diaria | Arrancar, parar, Ollama, Docker, problemas frecuentes |
| [DESPLIEGUE_PRODUCCION.md](DESPLIEGUE_PRODUCCION.md) | Sysadmin | Nginx, usuario BD lectura, seguridad, producción |

---

## Referencia de datos

| Recurso | Descripción |
|---------|-------------|
| [schema/mtd10.sql](schema/mtd10.sql) | Volcado pg_dump de la BD `mtd10` (escala 1:10 000) |
| [schema/README.md](schema/README.md) | Cómo restaurar y usar el volcado |

---

## Orden recomendado de lectura

```
0. CONVENCION_ESCALAS.md     → entender prefijos 10_, 25_, 100_…
1. GUIA_USO_SERVICIO.md     → levantar el servicio (mtd10 / 1:10 000)
1b. PRUEBAS_INICIALES.md    → probar health, schema y primera consulta NL
1c. MEJORAR_CALIDAD_SQL.md  → si falla la generación SQL (422)
2. ESQUEMA_MTD10.md         → tablas de la escala 1:10 000
3. INTEGRACION_WEB_QGIS.md  → conectar web o QGIS
4. EJECUCION_SERVICIO.md    → operación diaria
5. DESPLIEGUE_PRODUCCION.md → producción
```

---

## Relación con GeoNLQ

| Servicio | Carpeta | Base de datos | Puerto |
|----------|---------|---------------|--------|
| GeoNLQ | `../geonlq` | Infraestructura vial (puentes, viales) | 8000 |
| **MTD-NLQ** | `../mtdnlq` | Mapa Topográfico Digital (`mtd10`, `mtd25`…) | 8001 |

Comparten arquitectura (FastAPI + LLM + PostGIS) pero son servicios independientes.
