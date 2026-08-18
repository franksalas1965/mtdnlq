# Plugin QGIS MTD-NLQ

Plugin para **QGIS 3.40.x** que consume el servicio [MTD-NLQ](../mtdnlq/) y permite:

- Consultas en **lenguaje natural** sobre el Mapa Topográfico Digital
- Visualización según el `display_mode` de la API:
  - **map** — tabla de resultados + botón para **localizar** cada registro en el mapa (no carga todo el GeoJSON de golpe)
  - **table** — tabla con listados sin geometría
  - **summary** — tabla resumen (conteos, agregados, una fila)
- Panel de **explicación** cuando se solicita (`explain=true`)
- Panel opcional con el **SQL generado**
- **Exportar a Excel** (.xls) o CSV desde la pestaña Resultados
- **Configuración portable** guardada en el perfil de QGIS (URL, timeout, CRS, etc.)
- **Historial local** de consultas exitosas («Query Capsules»): búsqueda, reutilizar resultados, cargar GeoJSON en el mapa

---

## Historial local (Query Capsules)

Cada consulta **completada con éxito** se guarda automáticamente en:

```
%APPDATA%/MTD-NLQ/query_history/     (Windows, vía QStandardPaths)
├── history.db                        ← índice SQLite + búsqueda FTS5
└── capsules/{uuid}/                  ← una carpeta por consulta
    ├── capsule.mtdnlq.json           ← manifiesto (metadatos + rutas)
    ├── query.sql                     ← SQL reutilizable
    └── results.geojson               ← resultados (OGR/QGIS los abre directo)
```

En la pestaña **Historial** puede:

| Acción | Descripción |
|--------|-------------|
| **Ver resultados** | Restaura la respuesta en la pestaña Resultados (sin llamar al servidor) |
| **Usar pregunta** | Copia la pregunta a la pestaña Consulta |
| **Capa en mapa** | Añade `results.geojson` como capa OGR |
| **Carpeta** | Abre la cápsula en el explorador (compartir, respaldo) |
| **Buscar** | FTS5 sobre pregunta y SQL |

Límite por defecto: **150** entradas (`history_max_entries` en QSettings).

---

## Requisitos

| Componente | Versión |
|------------|---------|
| QGIS | 3.40.x |
| Servicio MTD-NLQ | En ejecución (p. ej. `http://localhost:8001`) |
| Python | El incluido en QGIS (sin pip extra) |

El plugin usa solo la biblioteca estándar de Python (`urllib`, `json`); no requiere instalar `requests`.

---

## Instalación

### Opción A — Carpeta de plugins de QGIS (recomendada)

1. Copie la carpeta `mtdnlq_qgis` completa al directorio de plugins de QGIS:

   **Windows (QGIS instalado):**
   ```
   %APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\
   ```

   Ejemplo:
   ```
   C:\Users\SU_USUARIO\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\mtdnlq_qgis
   ```

2. En QGIS: **Complementos → Gestionar e instalar complementos → Installed** (Instalados).
3. Active **MTD-NLQ**.
4. Aparecerá un icono en la barra de herramientas y el menú **Complementos → MTD-NLQ**.

### Opción B — Enlace simbólico (desarrollo)

Desde PowerShell (como administrador si hace falta):

```powershell
$plugins = "$env:APPDATA\QGIS\QGIS3\profiles\default\python\plugins"
New-Item -ItemType SymbolicLink -Path "$plugins\mtdnlq_qgis" -Target "D:\proyectos\AI\Analisis en lenguaje Natural\mtdnlq_qgis"
```

Reinicie QGIS tras instalar o actualizar el plugin.

---

## Configuración (portabilidad entre PCs)

Menú del panel → **Configuración…** o botón homónimo en el dock.

| Opción | Default | Descripción |
|--------|---------|-------------|
| URL base de la API | `http://localhost:8001` | Cambiar en cada PC según dónde corre MTD-NLQ |
| Tiempo de espera | 180 s | El LLM puede tardar varios minutos |
| Máximo de resultados | 100 | Límite enviado a la API |
| Formato de salida | GeoJSON | `geojson` o `table` |
| Incluir explicación | No | Pide texto explicativo del SQL |
| Mostrar SQL | Sí | Panel con la sentencia generada |
| CRS para resultados | EPSG:4267 | NAD27 del MTD |
| Color / grosor resaltado | #2563eb / 2 | Estilo al localizar en mapa |
| Quitar capa anterior | Sí | Solo una localización visible |

Los valores se guardan en **QSettings** (`MTD-NLQ` / `mtdnlq_qgis`) dentro del perfil de QGIS del usuario.

Use **Probar conexión** para validar `GET /api/v1/health` antes de consultar.

---

## Uso

1. Arranque MTD-NLQ (ver [GUIA_USO_SERVICIO.md](../mtdnlq/docs/GUIA_USO_SERVICIO.md)).
2. Abra el panel **MTD-NLQ — Consulta natural** (icono o menú).
3. Escriba una pregunta en español (mínimo 5 caracteres).
4. Opcional: marque **Incluir explicación**.
5. Pulse **Consultar** y espere (1–3 min con modelos locales).
6. Interprete el resultado:

| `display_mode` | Qué verá |
|----------------|----------|
| `map` + geometría | Tabla con columna **Mapa** (icono localizar) |
| `table` | Tabla de atributos |
| `summary` | Tabla Campo / Valor |
| Explicación | Área de texto arriba del resultado |

**Localizar en mapa:** en resultados con geometría, pulse el icono de zoom en la fila deseada. Se crea una capa temporal `MTD-NLQ — localizar: …` y el mapa hace zoom a ese registro.

---

## Preguntas de prueba

| Pregunta | Resultado esperado |
|----------|-------------------|
| ¿Cuántos ríos y arroyos hay? | `summary` — conteo |
| Dame los límites estatales | `map` — tabla + localizar |
| Lista las vías de comunicación | `map` — tabla + localizar |

Si recibe error HTTP 422, consulte [MEJORAR_CALIDAD_SQL.md](../mtdnlq/docs/MEJORAR_CALIDAD_SQL.md).

---

## Estructura del plugin

```
mtdnlq_qgis/
├── __init__.py           # classFactory
├── plugin.py             # Entrada QGIS
├── nlq_dock_widget.py    # Panel principal
├── result_panel.py       # Tabla / resumen / explicación
├── map_locator.py        # Localización puntual
├── api_client.py         # Cliente HTTP
├── query_worker.py       # Hilo en background
├── settings_manager.py   # QSettings
├── settings_dialog.py    # Diálogo de opciones
├── metadata.txt
├── icons/mtdnlq.svg
└── README.md
```

---

## Solución de problemas

| Problema | Acción |
|----------|--------|
| No conecta | Verificar URL en Configuración; probar `http://localhost:8001/api/v1/health` en navegador |
| Timeout | Aumentar tiempo de espera; usar modelo LLM más rápido o mayor RAM |
| 422 sql_generation_failed | Reformular pregunta o mejorar comentarios en BD / modelo mayor |
| Localizar no muestra nada | Comprobar CRS `EPSG:4267`; revisar que el feature tenga geometría |
| Plugin no aparece | Ruta correcta en `python/plugins`; reiniciar QGIS; revisar **Plugin Reloader** si desarrolla |

---

## Referencias

- [MTD-NLQ — Integración web/QGIS](../mtdnlq/docs/INTEGRACION_WEB_QGIS.md)
- [Pruebas iniciales del servicio](../mtdnlq/docs/PRUEBAS_INICIALES.md)
- Swagger API: `http://localhost:8001/docs`
