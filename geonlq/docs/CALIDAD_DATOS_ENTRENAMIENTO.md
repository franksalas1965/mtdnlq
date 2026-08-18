# GeoNLQ — Cómo determinar consultas exitosas para entrenamiento

**Versión:** 1.0  
**Propósito:** Criterios y proceso para seleccionar consultas reales de `query_history`  
que sean aptas para usarse como datos de entrenamiento en fine-tuning

---

## Índice

1. [El problema: éxito técnico ≠ éxito semántico](#1-el-problema)
2. [Filtros automáticos](#2-filtros-automáticos)
3. [Señales de fracaso sin revisión humana](#3-señales-de-fracaso-sin-revisión-humana)
4. [Feedback del usuario como fuente de verdad](#4-feedback-del-usuario-como-fuente-de-verdad)
5. [Revisión humana: cuándo y cómo](#5-revisión-humana-cuándo-y-cómo)
6. [Script de exportación de candidatas](#6-script-de-exportación-de-candidatas)
7. [Proceso completo de recolección periódica](#7-proceso-completo-de-recolección-periódica)
8. [Endpoint de feedback en la API](#8-endpoint-de-feedback-en-la-api)

---

## 1. El problema

Una consulta puede tener `status = 'success'` en `query_history` y aún así
ser un mal ejemplo de entrenamiento. Hay tres tipos de fallo silencioso:

```
Pregunta: "Dame los puentes con carga mayor a 10 toneladas en La Habana"

Caso A — Éxito real:
  SQL correcto, devuelve 8 puentes de La Habana con carga >= 10
  → APTA para entrenamiento ✓

Caso B — Éxito técnico, fallo semántico:
  SQL ejecuta sin error pero filtra por carga > 10 (excluye los de exactamente 10)
  o no filtra por provincia
  → NO APTA, el SQL está mal aunque no dio error ✗

Caso C — Éxito técnico, resultado vacío engañoso:
  SQL ejecuta sin error, devuelve 0 resultados
  porque el modelo generó un nombre de vía mal escrito
  → NO APTA ✗
```

---

## 2. Filtros automáticos

El primer nivel de filtrado es puramente automático. Aplícalo siempre
antes de cualquier revisión manual:

```sql
-- ============================================================
-- CONSULTA BASE: candidatas automáticas para entrenamiento
-- ============================================================
SELECT
    id,
    question,
    sql_generated,
    result_count,
    execution_ms,
    created_at
FROM query_history
WHERE
    -- Sin errores de ejecución
    status = 'success'
    AND error_msg IS NULL

    -- Devolvió resultados (lista vacía sospechosa)
    AND result_count > 0

    -- No devolvió demasiado (posible falta de filtros)
    AND result_count < 500

    -- Tiempo razonable (SQL eficiente)
    AND execution_ms < 15000

    -- Tiene SQL generado (no fue bloqueada)
    AND sql_generated IS NOT NULL
    AND LENGTH(sql_generated) > 20

    -- El SQL empieza correctamente
    AND UPPER(TRIM(sql_generated)) LIKE 'SELECT%'

    -- Período de tiempo reciente
    AND created_at > NOW() - INTERVAL '30 days'

ORDER BY created_at DESC;
```

### Qué descarta cada filtro y por qué

| Filtro | Descarta | Razón |
|--------|----------|-------|
| `status = 'success'` | Consultas con error de ejecución | SQL sintácticamente incorrecto |
| `result_count > 0` | Listas vacías | Probable fallo de filtrado o nombre mal escrito |
| `result_count < 500` | Resultados masivos | Posible ausencia de filtros WHERE |
| `execution_ms < 15000` | Consultas lentas | SQL ineficiente, posible falta de índices |
| `LENGTH(sql_generated) > 20` | SQL trivial | `SELECT 1` o similar, sin valor |
| `UPPER(...) LIKE 'SELECT%'` | Consultas bloqueadas | El validador las rechazó en otro intento |

---

## 3. Señales de fracaso sin revisión humana

Estas consultas pasaron los filtros automáticos pero tienen señales de alerta
que se pueden detectar con SQL adicional:

### 3.1 El usuario repitió la misma pregunta poco después

```sql
-- Consultas repetidas en menos de 10 minutos desde la misma IP
-- Indican insatisfacción con la respuesta anterior
SELECT DISTINCT q1.id, q1.question, q1.sql_generated
FROM query_history q1
WHERE EXISTS (
    SELECT 1 FROM query_history q2
    WHERE q2.client_ip   = q1.client_ip
      AND q2.id         != q1.id
      AND q2.created_at  BETWEEN q1.created_at
                              AND q1.created_at + INTERVAL '10 minutes'
      AND similarity(q2.question, q1.question) > 0.6  -- pg_trgm
)
AND q1.status = 'success';
-- Estas NO las incluyas en el dataset
```

### 3.2 El SQL ignora partes clave de la pregunta

```sql
-- Pregunta menciona provincia pero el SQL no filtra por ella
SELECT id, question, sql_generated
FROM query_history
WHERE status = 'success'
  AND (
      question ILIKE '%habana%'
      OR question ILIKE '%pinar%'
      OR question ILIKE '%matanzas%'
  )
  AND sql_generated NOT ILIKE '%provincia%'
  AND sql_generated NOT ILIKE '%municipio%'
  AND sql_generated NOT ILIKE '%habana%'
  AND sql_generated NOT ILIKE '%pinar%'
  AND sql_generated NOT ILIKE '%matanzas%';
-- Sospechosas: la pregunta tenía filtro geográfico pero el SQL no
```

### 3.3 El SQL no usa funciones espaciales cuando la pregunta lo requiere

```sql
-- Pregunta pide distancia/proximidad pero el SQL no usa ST_DWithin
SELECT id, question, sql_generated
FROM query_history
WHERE status = 'success'
  AND (
      question ILIKE '%cerca de%'
      OR question ILIKE '%metros de%'
      OR question ILIKE '%próximo%'
      OR question ILIKE '%próxima%'
  )
  AND sql_generated NOT ILIKE '%ST_DWithin%'
  AND sql_generated NOT ILIKE '%ST_Distance%'
  AND sql_generated NOT ILIKE '%ST_Buffer%';
-- Estas son errores seguros: faltó la función espacial
```

### 3.4 Resumen: consultas a EXCLUIR automáticamente

```sql
-- Vista auxiliar: consultas problemáticas detectadas automáticamente
CREATE OR REPLACE VIEW query_history_problematicas AS

-- Repetidas (insatisfacción del usuario)
SELECT id, 'repetida' AS motivo FROM query_history q1
WHERE EXISTS (
    SELECT 1 FROM query_history q2
    WHERE q2.client_ip = q1.client_ip AND q2.id != q1.id
      AND q2.created_at BETWEEN q1.created_at
                             AND q1.created_at + INTERVAL '10 minutes'
      AND similarity(q2.question, q1.question) > 0.6
)

UNION

-- Sin filtro espacial cuando la pregunta lo pide
SELECT id, 'falta_espacial' AS motivo FROM query_history
WHERE status = 'success'
  AND (question ILIKE '%cerca de%' OR question ILIKE '%metros de%')
  AND sql_generated NOT ILIKE '%ST_DWithin%'
  AND sql_generated NOT ILIKE '%ST_Distance%';
```

---

## 4. Feedback del usuario como fuente de verdad

La señal más fiable y de menor costo es que el propio usuario marque
si la respuesta fue útil. Requiere añadir una columna a `query_history`
y un endpoint a la API (ver sección 8).

```sql
-- Añadir columna de feedback a query_history
ALTER TABLE query_history
    ADD COLUMN IF NOT EXISTS feedback VARCHAR(10)
        CHECK (feedback IN ('util', 'incorrecto', 'parcial')),
    ADD COLUMN IF NOT EXISTS feedback_nota TEXT,
    ADD COLUMN IF NOT EXISTS feedback_at TIMESTAMP WITH TIME ZONE;

-- Índice para filtrar por feedback rápidamente
CREATE INDEX IF NOT EXISTS idx_query_history_feedback
    ON query_history (feedback)
    WHERE feedback IS NOT NULL;
```

Con feedback activado, el query de candidatas se simplifica enormemente:

```sql
-- Candidatas con feedback positivo confirmado — calidad garantizada
SELECT question, sql_generated
FROM query_history
WHERE feedback = 'util'
  AND status   = 'success'
ORDER BY feedback_at DESC;
```

### Escala de calidad por fuente

| Fuente | Calidad | Esfuerzo |
|--------|---------|---------|
| Feedback `util` confirmado por usuario | ★★★★★ | Ninguno (automático) |
| Revisión humana directa | ★★★★☆ | Alto |
| Filtros automáticos + sin señales de fallo | ★★★☆☆ | Mínimo |
| Generadas por plantillas (script) | ★★☆☆☆ | Mínimo |
| Sin filtrar de `query_history` | ★☆☆☆☆ | — |

---

## 5. Revisión humana: cuándo y cómo

No es necesario revisar todo manualmente. La regla práctica es:

**Si tienes < 200 candidatas automáticas → revisa todas.**  
**Si tienes > 200 candidatas → revisa una muestra del 20% y decide.**

### 5.1 Script de revisión por muestreo

```python
#!/usr/bin/env python3
"""
Revisión manual de candidatas para entrenamiento.
Uso: python revisar_candidatas.py candidatas.jsonl
"""
import json
import sys

aptas    = []
no_aptas = []

with open(sys.argv[1]) as f:
    candidatas = [json.loads(line) for line in f]

print(f"Total a revisar: {len(candidatas)}")
print("Responde: [s]í apta / [n]o apta / [p]arcial / [q]uit\n")

for i, c in enumerate(candidatas, 1):
    print(f"── {i}/{len(candidatas)} ──────────────────────────────────")
    print(f"PREGUNTA: {c['question']}")
    print(f"SQL:      {c['sql_generated']}")
    print(f"Resultados: {c.get('result_count', '?')} filas")
    print()

    resp = input("¿Apta? [s/n/p/q]: ").strip().lower()

    if resp == 'q':
        break
    elif resp == 's':
        aptas.append(c)
    elif resp == 'p':
        # Parcial: guardar pero marcar para revisar el SQL
        c['revision'] = 'parcial'
        aptas.append(c)
    else:
        no_aptas.append(c)

print(f"\nAptas:    {len(aptas)}")
print(f"No aptas: {len(no_aptas)}")

tasa = len(aptas) / (len(aptas) + len(no_aptas)) * 100 if aptas or no_aptas else 0
print(f"Tasa de calidad: {tasa:.0f}%")

if tasa >= 75:
    print("✓ Calidad suficiente — puedes usar todas las candidatas automáticas")
else:
    print("⚠ Calidad baja — revisa más antes de usar el dataset completo")

with open('aptas_revisadas.jsonl', 'w') as f:
    for c in aptas:
        f.write(json.dumps(c, ensure_ascii=False) + '\n')
```

### 5.2 Criterios de revisión rápida (30 segundos por consulta)

Al revisar manualmente, hazte estas tres preguntas:

```
1. ¿El SQL filtra exactamente lo que pide la pregunta?
   → Pregunta "carga > 10" y SQL dice "> 10"  ✓
   → Pregunta "carga > 10" y SQL dice ">= 10"  ✓ (aceptable)
   → Pregunta "carga > 10" y SQL no tiene WHERE ✗

2. ¿Usa las tablas correctas?
   → Pregunta sobre puentes y consulta tabla puentes  ✓
   → Pregunta sobre puentes y consulta tabla viales sin JOIN  ✗

3. ¿El resultado tiene sentido?
   → Devolvió 8 filas para puentes en una provincia  ✓
   → Devolvió 0 filas con filtros muy específicos  ✗ (sospechoso)
   → Devolvió 450 filas sin filtros claros  ✗ (demasiado)
```

---

## 6. Script de exportación de candidatas

Guarda este script en `modelos_locales/scripts/exportar_candidatas.py`:

```python
#!/usr/bin/env python3
"""
GeoNLQ — Exportar candidatas de query_history para entrenamiento.
Aplica filtros automáticos y genera JSONL listo para revisión o fine-tuning.

Uso:
  python exportar_candidatas.py --days 30 --output candidatas.jsonl
  python exportar_candidatas.py --days 30 --solo-feedback --output aptas.jsonl
"""
import argparse
import json
import os
import psycopg2
from datetime import datetime

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:Gispostgres123!@localhost:5434/geonlq"
)

QUERY_CANDIDATAS = """
SELECT
    id,
    question,
    sql_generated,
    result_count,
    execution_ms,
    created_at::text,
    COALESCE(feedback, 'sin_feedback') AS feedback
FROM query_history
WHERE
    status       = 'success'
    AND error_msg IS NULL
    AND result_count > 0
    AND result_count < 500
    AND execution_ms < 15000
    AND sql_generated IS NOT NULL
    AND LENGTH(sql_generated) > 20
    AND UPPER(TRIM(sql_generated)) LIKE 'SELECT%%'
    AND created_at > NOW() - INTERVAL '{days} days'
    -- Excluir repetidas (insatisfacción)
    AND id NOT IN (
        SELECT DISTINCT q1.id
        FROM query_history q1
        WHERE EXISTS (
            SELECT 1 FROM query_history q2
            WHERE q2.client_ip = q1.client_ip AND q2.id != q1.id
              AND q2.created_at BETWEEN q1.created_at
                                     AND q1.created_at + INTERVAL '10 minutes'
              AND similarity(q2.question, q1.question) > 0.6
        )
    )
ORDER BY
    CASE feedback WHEN 'util' THEN 1 WHEN 'sin_feedback' THEN 2 ELSE 3 END,
    created_at DESC;
"""

QUERY_SOLO_FEEDBACK = """
SELECT id, question, sql_generated, result_count, execution_ms,
       created_at::text, feedback
FROM query_history
WHERE feedback = 'util' AND status = 'success'
ORDER BY feedback_at DESC;
"""

def formato_chat(question: str, sql: str) -> dict:
    """Formato de entrenamiento compatible con Qwen2.5 / Llama3."""
    return {
        "messages": [
            {"role": "system",    "content": "Traduce la pregunta en español a SQL para PostGIS."},
            {"role": "user",      "content": question},
            {"role": "assistant", "content": sql.strip()},
        ]
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days",           type=int,  default=30)
    parser.add_argument("--output",         type=str,  default="candidatas.jsonl")
    parser.add_argument("--solo-feedback",  action="store_true",
                        help="Exportar solo las marcadas como útiles por el usuario")
    parser.add_argument("--formato-chat",   action="store_true",
                        help="Exportar en formato de entrenamiento (listo para fine-tuning)")
    args = parser.parse_args()

    conn   = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    if args.solo_feedback:
        cursor.execute(QUERY_SOLO_FEEDBACK)
        print("Modo: solo feedback positivo confirmado")
    else:
        cursor.execute(QUERY_CANDIDATAS.format(days=args.days))
        print(f"Modo: filtros automáticos — últimos {args.days} días")

    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    candidatas = [dict(zip(cols, row)) for row in rows]
    conn.close()

    # Estadísticas
    total       = len(candidatas)
    con_feedback = sum(1 for c in candidatas if c.get('feedback') == 'util')
    print(f"Total candidatas:          {total}")
    print(f"Con feedback positivo:     {con_feedback}")
    print(f"Sin feedback (automáticas):{total - con_feedback}")

    # Exportar
    with open(args.output, 'w', encoding='utf-8') as f:
        for c in candidatas:
            if args.formato_chat:
                registro = formato_chat(c['question'], c['sql_generated'])
            else:
                # Incluir metadatos para revisión
                registro = {
                    "id":           c['id'],
                    "question":     c['question'],
                    "sql_generated":c['sql_generated'],
                    "result_count": c['result_count'],
                    "execution_ms": c['execution_ms'],
                    "feedback":     c['feedback'],
                    "created_at":   c['created_at'],
                }
            f.write(json.dumps(registro, ensure_ascii=False) + '\n')

    print(f"\n✓ Exportadas {total} candidatas → {args.output}")
    if not args.formato_chat:
        print("  Para revisar manualmente: python revisar_candidatas.py", args.output)
        print("  Para exportar listas para training añade --formato-chat")

if __name__ == "__main__":
    main()
```

### Uso del script

```bash
# Exportar candidatas de los últimos 30 días para revisión manual
python exportar_candidatas.py --days 30 --output candidatas.jsonl

# Exportar solo las confirmadas por el usuario, listas para fine-tuning
python exportar_candidatas.py --solo-feedback --formato-chat --output train_reales.jsonl

# Mezclar con el dataset generado por plantillas
cat ../datos/train.jsonl train_reales.jsonl | shuf > train_combinado.jsonl
wc -l train_combinado.jsonl
```

---

## 7. Proceso completo de recolección periódica

Recomendación: ejecutar este proceso una vez al mes.

```
SEMANA 1-4: El sistema corre en producción
            query_history acumula consultas reales
            Los usuarios marcan feedback (si está activado)

─────────────────────────────────────────────────────
FIN DE MES: Proceso de recolección (1-2 horas)
─────────────────────────────────────────────────────

□ Paso 1 — Exportar candidatas
  python exportar_candidatas.py --days 30 --output candidatas_mes.jsonl

□ Paso 2 — Ver estadísticas
  wc -l candidatas_mes.jsonl
  Si hay < 50 candidatas → no vale la pena re-entrenar este mes, esperar

□ Paso 3 — Muestreo de calidad (si no hay feedback activado)
  python revisar_candidatas.py candidatas_mes.jsonl
  Revisar 20-30 ejemplos → calcular tasa de calidad
  Si tasa >= 75% → usar todas
  Si tasa < 75%  → revisar más o descartar lote

□ Paso 4 — Exportar en formato de entrenamiento
  python exportar_candidatas.py --days 30 --formato-chat --output train_nuevas.jsonl

□ Paso 5 — Combinar con dataset histórico
  cat datos/train_historico.jsonl train_nuevas.jsonl | shuf > datos/train_v2.jsonl
  # Guardar las nuevas en el histórico para el próximo mes
  cat train_nuevas.jsonl >> datos/train_historico.jsonl

□ Paso 6 — Re-entrenar (si hay >= 100 consultas nuevas de calidad)
  Ver: ESCALADO.md → Paso 4 (Re-entrenar el modelo en Colab)

□ Paso 7 — Actualizar historial de versiones en ESCALADO.md
```

---

## 8. Endpoint de feedback en la API

Añadir este endpoint a `src/geonlq/api/routes.py` para que las aplicaciones
cliente puedan marcar si una consulta fue útil:

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..db.database import get_db
from sqlalchemy.orm import Session
from fastapi import Depends

router = APIRouter()

class FeedbackRequest(BaseModel):
    feedback: str           # 'util', 'incorrecto', 'parcial'
    nota: Optional[str] = None

@router.post("/query/{query_id}/feedback")
async def registrar_feedback(
    query_id: int,
    body: FeedbackRequest,
    db: Session = Depends(get_db)
):
    """
    Marca una consulta como útil, incorrecta o parcial.
    Úsalo desde tu aplicación cliente con un botón de pulgar arriba/abajo.
    """
    valores_validos = {'util', 'incorrecto', 'parcial'}
    if body.feedback not in valores_validos:
        raise HTTPException(
            status_code=422,
            detail=f"feedback debe ser uno de: {valores_validos}"
        )

    resultado = db.execute(
        """UPDATE query_history
           SET feedback      = :feedback,
               feedback_nota = :nota,
               feedback_at   = NOW()
           WHERE id = :id
           RETURNING id""",
        {"feedback": body.feedback, "nota": body.nota, "id": query_id}
    ).fetchone()

    if not resultado:
        raise HTTPException(status_code=404, detail="Consulta no encontrada")

    return {"id": query_id, "feedback": body.feedback, "registrado": True}
```

### Ejemplo de uso desde una aplicación cliente

```bash
# El usuario marcó la consulta ID 42 como útil
curl -X POST http://localhost:8000/api/v1/query/42/feedback \
  -H "Content-Type: application/json" \
  -d '{"feedback": "util"}'

# El usuario marcó como incorrecta y dejó nota
curl -X POST http://localhost:8000/api/v1/query/43/feedback \
  -H "Content-Type: application/json" \
  -d '{"feedback": "incorrecto", "nota": "No filtró por provincia"}'
```

---

## Resumen visual del flujo completo

```
query_history (producción)
        │
        ▼
Filtros automáticos ──────────────────── Excluye:
(SQL, result_count,                      · Errores de ejecución
 execution_ms,                           · Listas vacías
 repetidas)                              · Resultados masivos
        │                                · Consultas repetidas
        ▼
Candidatas automáticas (~70% precisión)
        │
        ├── Con feedback 'util' ──────── Calidad ★★★★★ → directas a train
        │
        └── Sin feedback ──────────────► Muestreo manual 20%
                                                │
                                         Tasa >= 75% → usar todas
                                         Tasa <  75% → revisar más
                                                │
                                         aptas_revisadas.jsonl
                                                │
                                                ▼
                              Mezclar con dataset histórico
                                                │
                                                ▼
                                       Re-entrenar en Colab
                                                │
                                                ▼
                                    Nuevo modelo desplegado
```
