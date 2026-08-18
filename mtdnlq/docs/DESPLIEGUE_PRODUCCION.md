# MTD-NLQ — Despliegue en producción

**Servicio:** MTD-NLQ — consultas NL sobre Mapa Topográfico Digital  
**Base de datos:** `mtd10` (PostGIS, escala 1:10 000)  
**Puerto API interno:** 8001

Para desarrollo y arranque diario, ver [EJECUCION_SERVICIO.md](EJECUCION_SERVICIO.md).

---

## Índice

1. [Requisitos](#1-requisitos)
2. [Usuario de BD de solo lectura](#2-usuario-de-bd-de-solo-lectura)
3. [Instalación del servicio](#3-instalación-del-servicio)
4. [Variables de entorno](#4-variables-de-entorno)
5. [Ollama en producción](#5-ollama-en-producción)
6. [systemd + Docker](#6-systemd--docker)
7. [Nginx como proxy inverso](#7-nginx-como-proxy-inverso)
8. [Verificación](#8-verificación)
9. [Seguridad](#9-seguridad)
10. [Optimizar mtd10 para el LLM](#10-optimizar-mtd10-para-el-llm)

---

## 1. Requisitos

| Componente | Recomendado |
|------------|-------------|
| SO | Ubuntu 22.04 / 24.04 LTS |
| RAM | 16 GB (con Ollama local) |
| PostgreSQL | 12+ con PostGIS 3.x |
| BD | `mtd10` cargada (volcado en `docs/schema/mtd10.sql`) |
| Docker | Engine + Compose v2 |
| Ollama | Opcional; alternativa OpenAI/Anthropic |

---

## 2. Usuario de BD de solo lectura

No uses el superusuario `postgres` en producción. MTD-NLQ genera SQL dinámicamente.

```sql
-- Conectar como postgres a mtd10
CREATE USER mtdnlq_reader WITH PASSWORD 'contraseña_segura';

GRANT CONNECT ON DATABASE mtd10 TO mtdnlq_reader;

-- Esquemas temáticos MTD (10_*)
GRANT USAGE ON SCHEMA
  "10_areas_verdes_y_terrenos",
  "10_hidrografia",
  "10_hidrografia_presas",
  "10_limites_estatales",
  "10_objetivos_economicos",
  "10_provincias_y_cercas",
  "10_puntos_de_apoyo",
  "10_puntos_poblados",
  "10_red_vial",
  "10_relieve"
TO mtdnlq_reader;

GRANT SELECT ON ALL TABLES IN SCHEMA
  "10_areas_verdes_y_terrenos",
  "10_hidrografia",
  "10_hidrografia_presas",
  "10_limites_estatales",
  "10_objetivos_economicos",
  "10_provincias_y_cercas",
  "10_puntos_de_apoyo",
  "10_puntos_poblados",
  "10_red_vial",
  "10_relieve"
TO mtdnlq_reader;
```

Si añades esquemas nuevos (ej. `10_marco_geografico`), repite `GRANT USAGE` y `GRANT SELECT`.

---

## 3. Instalación del servicio

```bash
sudo mkdir -p /opt/mtdnlq
sudo cp -r /ruta/al/proyecto/mtdnlq/* /opt/mtdnlq/
cd /opt/mtdnlq

cp .env.docker.example .env
chmod 600 .env
nano .env   # credenciales mtd10, LLM, CORS

docker compose -f docker-compose.external-db.yml build
docker compose -f docker-compose.external-db.yml up -d
```

---

## 4. Variables de entorno

```env
POSTGRES_HOST=host.docker.internal
POSTGRES_PORT=5433
POSTGRES_DB=mtd10
POSTGRES_USER=mtdnlq_reader
POSTGRES_PASSWORD=contraseña_segura

MTDNLQ_HOST_PORT=8001

LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:1.5b
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_TIMEOUT_SECONDS=180

ALLOWED_SCHEMAS=10_areas_verdes_y_terrenos,10_hidrografia,10_hidrografia_presas,10_limites_estatales,10_objetivos_economicos,10_provincias_y_cercas,10_puntos_de_apoyo,10_puntos_poblados,10_red_vial,10_relieve

MAX_RESULTS=100
SQL_TIMEOUT=30
CORS_ORIGINS=https://visor.tu-dominio.cu
LOG_LEVEL=INFO
DEBUG=false
```

---

## 5. Ollama en producción

```bash
# Instalar Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Escuchar en todas las interfaces (para Docker)
sudo mkdir -p /etc/systemd/system/ollama.service.d
printf '%s\n' '[Service]' 'Environment="OLLAMA_HOST=0.0.0.0:11434"' \
  | sudo tee /etc/systemd/system/ollama.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl enable ollama && sudo systemctl start ollama

ollama pull qwen2.5-coder:1.5b
```

Restringe el puerto 11434 con firewall a localhost y red Docker.

---

## 6. systemd + Docker

Ver unidad completa en [EJECUCION_SERVICIO.md §5](EJECUCION_SERVICIO.md#5-arranque-automático-tras-reinicio).

```bash
sudo systemctl enable mtdnlq-docker
sudo systemctl start mtdnlq-docker
```

---

## 7. Nginx como proxy inverso

MTD-NLQ escucha en `localhost:8001`. Nginx expone HTTPS al exterior.

```nginx
server {
    listen 443 ssl;
    server_name mtd.tu-dominio.cu;

    ssl_certificate     /etc/ssl/certs/mtdnlq.crt;
    ssl_certificate_key /etc/ssl/private/mtdnlq.key;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_read_timeout 180s;
        proxy_connect_timeout 10s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Los clientes web y QGIS apuntan a `https://mtd.tu-dominio.cu/api/v1/query`.

---

## 8. Verificación

```bash
curl -s http://localhost:8001/api/v1/health | python3 -m json.tool
curl -s http://localhost:8001/api/v1/schema | python3 -m json.tool

curl -s -X POST http://localhost:8001/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question":"¿Cuántos ríos y arroyos hay?","output_format":"geojson"}' \
  | python3 -m json.tool
```

Comprobar que el SQL generado usa tablas reales (ej. `"10_hidrografia".rios_y_arroyos_lineal`).

---

## 9. Seguridad

- Usuario BD con **solo SELECT** sobre esquemas `10_*`.
- Validador SQL interno bloquea `UPDATE`, `DELETE`, `DROP`, etc.
- No exponer puerto 8001 directamente a Internet; usar Nginx + TLS.
- `CORS_ORIGINS` con dominios concretos, no `*` en producción.
- Proteger `.env` con `chmod 600`.
- Ollama en red interna; no exponer 11434 públicamente.

---

## 10. Optimizar mtd10 para el LLM

Los comentarios de PostgreSQL se incluyen en el prompt del LLM:

```sql
COMMENT ON TABLE "10_hidrografia".rios_y_arroyos_lineal IS
  'Cursos de agua: ríos y arroyos del MTD 1:10000';

COMMENT ON COLUMN "10_puntos_poblados".ciudad_puntual.cantidad_habitantes IS
  'Número de habitantes del asentamiento';
```

Tras añadir comentarios:

```bash
curl -s "http://localhost:8001/api/v1/schema?refresh=true"
# o reiniciar el contenedor
docker compose -f docker-compose.external-db.yml restart mtdnlq
```

Referencia de tablas: [ESQUEMA_MTD10.md](ESQUEMA_MTD10.md).  
Guía ampliada (comentarios, modelo, preguntas): [MEJORAR_CALIDAD_SQL.md](MEJORAR_CALIDAD_SQL.md).

---

## Comandos útiles

| Acción | Comando |
|--------|---------|
| Ver logs | `docker compose -f docker-compose.external-db.yml logs -f mtdnlq` |
| Reiniciar API | `docker compose -f docker-compose.external-db.yml restart mtdnlq` |
| Actualizar código | `git pull` + `docker compose ... build mtdnlq` + `up -d` |
