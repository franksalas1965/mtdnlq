# GeoNLQ — Guía de Fine-Tuning con QLoRA

**Versión:** 1.0  
**Modelo base:** Qwen2.5-Coder-1.5B-Instruct  
**Técnica:** QLoRA (Quantized Low-Rank Adaptation)  
**Plataforma de entrenamiento:** Google Colab (GPU T4 gratuita)  
**Tiempo estimado total:** 3–4 horas (primera vez)

---

## Índice

1. [¿Qué hace el fine-tuning y por qué es necesario?](#1-qué-hace-el-fine-tuning-y-por-qué-es-necesario)
2. [Requisitos previos](#2-requisitos-previos)
3. [Paso 1 — Generar los datos de entrenamiento](#3-paso-1--generar-los-datos-de-entrenamiento)
4. [Paso 2 — Preparar Google Colab](#4-paso-2--preparar-google-colab)
5. [Paso 3 — Entrenar el modelo (QLoRA)](#5-paso-3--entrenar-el-modelo-qlora)
6. [Paso 4 — Exportar a GGUF para Ollama](#6-paso-4--exportar-a-gguf-para-ollama)
7. [Paso 5 — Importar en Ollama y desplegar](#7-paso-5--importar-en-ollama-y-desplegar)
8. [Paso 6 — Verificar el modelo entrenado](#8-paso-6--verificar-el-modelo-entrenado)
9. [Solución de problemas frecuentes](#9-solución-de-problemas-frecuentes)
10. [Referencia de parámetros](#10-referencia-de-parámetros)
11. [Checklist completo](#11-checklist-completo)

---

## 1. ¿Qué hace el fine-tuning y por qué es necesario?

El modelo base `qwen2.5-coder:1.5b` conoce SQL y PostGIS en general, pero no conoce
tu esquema específico (tablas `puentes`, `viales`, `municipios`) ni el vocabulario
de tus usuarios. El fine-tuning le enseña eso mediante ejemplos:

```
Antes del fine-tuning:
  Pregunta: "Dame los puentes que soporten 10 toneladas"
  Respuesta: SELECT * FROM bridges WHERE max_load >= 10   ← columna y tabla incorrectas

Después del fine-tuning:
  Pregunta: "Dame los puentes que soporten 10 toneladas"
  Respuesta: SELECT codigo, nombre, carga_maxima_tn ...
             FROM puentes WHERE carga_maxima_tn >= 10 LIMIT 100;  ✓
```

**¿Qué se entrena?**  
No se modifica el modelo completo. La técnica QLoRA añade matrices pequeñas
(adaptadores LoRA) que se entrenan sobre el modelo base congelado. Esto permite
entrenar en una GPU modesta como la T4 gratuita de Colab (~3 GB VRAM usados
de los 16 disponibles).

---

## 2. Requisitos previos

### En tu máquina local
- Python 3.10+ con el entorno virtual del proyecto activo
- Script `generate_training_data.py` disponible en `modelos_locales/scripts/`
- Ollama instalado y funcionando (`ollama --version`)
- Al menos 2 GB libres en disco para el modelo GGUF final

### En Google Colab
- Cuenta de Google (gratuita es suficiente)
- GPU T4 activada en Colab (Runtime → Change runtime type → T4 GPU)
- Google Drive con ~5 GB libres (para guardar el adaptador y el GGUF)

### Archivos del proyecto necesarios
```
modelos_locales/
├── scripts/
│   ├── generate_training_data.py   ← genera los datos
│   └── finetune_qlora.py           ← script de entrenamiento
└── ollama/
    └── Modelfile                   ← configuración para Ollama
```

---

## 3. Paso 1 — Generar los datos de entrenamiento

Ejecuta esto en tu máquina local (WSL), desde la carpeta del proyecto:

```bash
cd "/mnt/d/proyectos/AI/Analisis en lenguaje Natural/modelos_locales/scripts"

# Activar entorno virtual si no está activo
source ~/geonlq/.venv/bin/activate

# Generar dataset con 1500 ejemplos y dividir en train/eval
python generate_training_data.py \
    --output ../datos/dataset.jsonl \
    --count 1500 \
    --format chat \
    --split

# Verificar que se generaron correctamente
wc -l ../datos/train.jsonl ../datos/eval.jsonl
```

Deberías ver algo como:
```
1350 ../datos/train.jsonl
 150 ../datos/eval.jsonl
```

**Revisar una muestra antes de continuar:**

```bash
# Ver 5 ejemplos aleatorios del dataset de entrenamiento
python3 -c "
import json, random
lines = open('../datos/train.jsonl').readlines()
for line in random.sample(lines, 5):
    ex = json.loads(line)
    msgs = ex['messages']
    print('PREGUNTA:', msgs[1]['content'])
    print('SQL:     ', msgs[2]['content'][:100])
    print('---')
"
```

Si los ejemplos se ven correctos (pregunta en español → SQL válido), continúa.  
Si hay algo raro, revisa `generate_training_data.py` antes de entrenar.

---

## 4. Paso 2 — Preparar Google Colab

### 4.1 Abrir un nuevo notebook

1. Ve a [colab.research.google.com](https://colab.research.google.com)
2. Crea un nuevo notebook: **File → New notebook**
3. Activa la GPU T4: **Runtime → Change runtime type → T4 GPU → Save**
4. Verifica que tienes GPU: ejecuta en una celda:
   ```python
   !nvidia-smi
   # Debes ver: Tesla T4, 15360 MiB
   ```

### 4.2 Montar Google Drive

```python
from google.colab import drive
drive.mount('/content/drive')

# Crear carpeta de trabajo en Drive
import os
os.makedirs('/content/drive/MyDrive/geonlq', exist_ok=True)
print("✓ Drive montado")
```

### 4.3 Instalar dependencias

```python
# Instalar librerías necesarias (tarda ~3 minutos)
!pip install -q \
    transformers==4.46.0 \
    peft==0.13.0 \
    trl==0.12.0 \
    bitsandbytes==0.44.1 \
    accelerate==1.1.0 \
    datasets==3.1.0 \
    scipy

print("✓ Dependencias instaladas")
```

> **Nota:** Las versiones son importantes. Si usas versiones distintas pueden
> aparecer incompatibilidades entre `peft`, `trl` y `transformers`.

### 4.4 Subir los datos de entrenamiento

**Opción A — Subir desde tu computadora (más simple):**

```python
from google.colab import files

print("Selecciona train.jsonl")
uploaded = files.upload()   # selecciona train.jsonl

print("Selecciona eval.jsonl")
uploaded = files.upload()   # selecciona eval.jsonl

# Mover a Drive para no perderlos si reinicia Colab
!cp train.jsonl /content/drive/MyDrive/geonlq/
!cp eval.jsonl  /content/drive/MyDrive/geonlq/
print("✓ Datos subidos y guardados en Drive")
```

**Opción B — Si ya los tienes en Drive:**

```python
!cp /content/drive/MyDrive/geonlq/train.jsonl /content/
!cp /content/drive/MyDrive/geonlq/eval.jsonl  /content/
print("✓ Datos copiados desde Drive")
```

### 4.5 Subir el script de entrenamiento

```python
from google.colab import files
print("Selecciona finetune_qlora.py")
files.upload()
```

---

## 5. Paso 3 — Entrenar el modelo (QLoRA)

### 5.1 Ejecutar el entrenamiento

```python
# Lanzar el entrenamiento
# Tarda entre 20 y 40 minutos con ~1350 ejemplos en T4
!python finetune_qlora.py \
    --train_file /content/train.jsonl \
    --eval_file  /content/eval.jsonl \
    --output_dir /content/geonlq-sql-adapter \
    --num_epochs 3

print("✓ Entrenamiento completado")
```

### 5.2 Qué verás durante el entrenamiento

El script imprime el progreso cada 50 pasos. Esto es lo que debes observar:

```
Epoch 1/3:
  Step  50 | train_loss: 1.82 | eval_loss: 1.79   ← empieza a aprender
  Step 100 | train_loss: 1.45 | eval_loss: 1.41
  Step 150 | train_loss: 1.12 | eval_loss: 1.08

Epoch 2/3:
  Step 200 | train_loss: 0.89 | eval_loss: 0.92
  Step 250 | train_loss: 0.71 | eval_loss: 0.78

Epoch 3/3:
  Step 300 | train_loss: 0.58 | eval_loss: 0.74   ← converge bien
  Step 350 | train_loss: 0.52 | eval_loss: 0.71
```

**Señales de buen entrenamiento:**
- `train_loss` baja consistentemente cada epoch
- `eval_loss` baja junto con `train_loss` o se mantiene estable
- Al final converge entre 0.4 y 0.8

**Señales de problema:**
- `eval_loss` sube mientras `train_loss` sigue bajando → overfitting
  (solución: reducir `--num_epochs` a 2)
- `train_loss` no baja de 1.5 → datos con problemas o learning rate muy bajo
- Error de memoria CUDA → reducir `per_device_train_batch_size` a 1

### 5.3 Guardar el adaptador en Drive inmediatamente

```python
# Copiar el adaptador a Drive para no perderlo si Colab desconecta
!cp -r /content/geonlq-sql-adapter \
       /content/drive/MyDrive/geonlq/geonlq-sql-adapter

# Verificar qué se guardó
!ls -lh /content/drive/MyDrive/geonlq/geonlq-sql-adapter/
```

Deberías ver:
```
adapter_config.json          ← configuración LoRA
adapter_model.safetensors    ← pesos entrenados (~10-40 MB)
tokenizer.json
tokenizer_config.json
special_tokens_map.json
```

> **Importante:** Guarda el adaptador en Drive antes de continuar.
> Si Colab se desconecta y no lo guardaste, pierdes el entrenamiento.

---

## 6. Paso 4 — Exportar a GGUF para Ollama

Este paso convierte el modelo al formato que usa Ollama para ejecutarse
en CPU. Son 4 sub-pasos: instalar llama.cpp, fusionar, convertir, cuantizar.

### 6.1 Subir el script de exportación

```python
from google.colab import files
print("Selecciona export_to_gguf.sh")
files.upload()
!chmod +x export_to_gguf.sh
```

### 6.2 Ejecutar la exportación completa

```python
# Este proceso tarda entre 15 y 25 minutos
# Necesita ~8 GB de RAM en Colab (el modelo fusionado en float16)
!bash export_to_gguf.sh
```

El script hace automáticamente:

```
[1/4] Clona llama.cpp (si no existe)          ~2 min
[2/4] Fusiona modelo base + adaptador LoRA    ~5 min
      → crea geonlq-sql-merged/ (~3 GB)
[3/4] Convierte a GGUF float16                ~5 min
      → crea geonlq-sql-gguf/geonlq-sql-f16.gguf (~3 GB)
[4/4] Cuantiza a Q4_K_M                       ~3 min
      → crea geonlq-sql-gguf/geonlq-sql-Q4_K_M.gguf (~900 MB)
```

### 6.3 Verificar el archivo final

```python
!ls -lh geonlq-sql-gguf/
# Debes ver:
# geonlq-sql-f16.gguf      ~3.0 GB  (intermedio, puedes borrarlo)
# geonlq-sql-Q4_K_M.gguf  ~900 MB  (este es el que necesitas)
```

### 6.4 Guardar el GGUF en Drive

```python
# Guardar el GGUF final en Drive
!cp geonlq-sql-gguf/geonlq-sql-Q4_K_M.gguf \
   /content/drive/MyDrive/geonlq/

# Eliminar archivos intermedios para liberar espacio
!rm -f geonlq-sql-gguf/geonlq-sql-f16.gguf
!rm -rf geonlq-sql-merged/

print("✓ GGUF guardado en Drive")
!ls -lh /content/drive/MyDrive/geonlq/
```

### 6.5 Descargar el GGUF a tu computadora

```python
# Opción A: descargar directamente desde Colab
from google.colab import files
files.download('geonlq-sql-gguf/geonlq-sql-Q4_K_M.gguf')
# → Se descarga a tu carpeta de Descargas de Windows
```

```python
# Opción B: si prefieres descargarlo manualmente desde Drive
# Ve a drive.google.com → Mi unidad → geonlq → descarga el .gguf
```

---

## 7. Paso 5 — Importar en Ollama y desplegar

Estos pasos se ejecutan en **WSL** en tu máquina local.

### 7.1 Copiar el GGUF al proyecto

```bash
# El archivo se descargó en la carpeta Descargas de Windows
# Copiarlo al directorio de Ollama del proyecto
cp "/mnt/c/Users/frank/Downloads/geonlq-sql-Q4_K_M.gguf" \
   "/mnt/d/proyectos/AI/Analisis en lenguaje Natural/modelos_locales/ollama/"

# Verificar que llegó correctamente
ls -lh "/mnt/d/proyectos/AI/Analisis en lenguaje Natural/modelos_locales/ollama/"
```

### 7.2 Crear el modelo en Ollama

```bash
cd "/mnt/d/proyectos/AI/Analisis en lenguaje Natural/modelos_locales/ollama"

# Asegurarse de que Ollama está corriendo
ollama list

# Crear el modelo fine-tuneado (usa el Modelfile del proyecto)
ollama create geonlq-sql -f Modelfile

# Verificar que se creó
ollama list
# Debes ver: geonlq-sql   ...   ~900 MB
```

> **El Modelfile** en `modelos_locales/ollama/Modelfile` apunta a
> `./geonlq-sql-Q4_K_M.gguf` y define el SYSTEM prompt con el esquema.
> Si cambiaste algo en el esquema, actualiza el Modelfile antes de este paso.

### 7.3 Probar el modelo directamente en Ollama

```bash
# Prueba rápida desde la terminal
ollama run geonlq-sql \
  "Dame los puentes con carga mayor a 10 toneladas"

# Resultado esperado (solo SQL, sin explicaciones):
# SELECT codigo, nombre, carga_maxima_tn, longitud_m, estado,
#        ST_AsGeoJSON(geom)::json AS geometry
# FROM puentes
# WHERE carga_maxima_tn >= 10
# ORDER BY carga_maxima_tn DESC LIMIT 100;
```

```bash
# Prueba con consulta compleja
ollama run geonlq-sql \
  "Puentes que pudieran estar a menos de 500 metros de la Carretera Central"

# Resultado esperado:
# SELECT p.codigo, p.nombre, p.carga_maxima_tn, p.estado,
#        ROUND(ST_Distance(p.geom::geography, v.geom::geography)::numeric, 2) AS distancia_m,
#        ST_AsGeoJSON(p.geom)::json AS geometry
# FROM puentes p
# JOIN viales v ON ST_DWithin(p.geom::geography, v.geom::geography, 500)
# WHERE v.nombre ILIKE '%carretera central%'
# ORDER BY distancia_m LIMIT 100;
```

### 7.4 Configurar el servicio GeoNLQ para usar el nuevo modelo

```bash
# Editar el .env del servicio
nano ~/geonlq/.env

# Cambiar la línea:
LLM_MODEL=qwen2.5-coder:1.5b      ← modelo base (anterior)
# Por:
LLM_MODEL=geonlq-sql               ← modelo fine-tuneado (nuevo)

# Guardar y salir: Ctrl+O, Enter, Ctrl+X
```

### 7.5 Reiniciar el servicio GeoNLQ

```bash
# Detener el servicio actual
pkill -f "uvicorn geonlq.main:app"

# Esperar 2 segundos y arrancar de nuevo
sleep 2
cd ~/geonlq
source .venv/bin/activate
uvicorn geonlq.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 8. Paso 6 — Verificar el modelo entrenado

### 8.1 Pruebas funcionales básicas

```bash
BASE="http://localhost:8000/api/v1"

# Prueba 1: consulta simple
curl -s -X POST $BASE/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Dame los puentes en mal estado", "include_geometry": false}' \
  | python3 -m json.tool

# Prueba 2: con carga mínima
curl -s -X POST $BASE/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Puentes que soporten al menos 20 toneladas", "include_geometry": false}' \
  | python3 -m json.tool

# Prueba 3: consulta espacial (la del usuario)
curl -s -X POST $BASE/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Dame los puentes que pudieran estar a menos de 500 metros de la Carretera Central", "include_geometry": false}' \
  | python3 -m json.tool

# Prueba 4: consulta de tramo (la consulta objetivo del proyecto)
curl -s -X POST $BASE/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Dame los puentes de la Carretera Central de Pinar del Río a La Habana que soporten 10 toneladas", "include_geometry": false}' \
  | python3 -m json.tool
```

### 8.2 Qué revisar en cada respuesta

```json
{
  "sql_generated": "SELECT p.codigo ...",   ← ¿tiene sentido el SQL?
  "result_count": 3,                        ← ¿devolvió resultados?
  "execution_ms": 1250,                     ← ¿tardó menos de 30 seg?
  "status": "success",                      ← sin errores
  "results": [ ... ]
}
```

Si `status` es `error`, revisa `error_msg` para entender qué falló.

### 8.3 Comparar con el modelo base

Para cuantificar la mejora, ejecuta las mismas consultas con el modelo base
y compara la calidad del SQL generado:

```bash
# Cambiar temporalmente al modelo base en .env
LLM_MODEL=qwen2.5-coder:1.5b

# Ejecutar las mismas pruebas y anotar los resultados

# Volver al modelo fine-tuneado
LLM_MODEL=geonlq-sql
```

### 8.4 Criterios de aceptación del modelo

Antes de considerar el fine-tuning exitoso, verifica:

- [ ] Consultas simples (1 tabla): SQL correcto en >90% de los casos
- [ ] Consultas con JOIN: SQL correcto en >80% de los casos
- [ ] Consultas espaciales (ST_DWithin): SQL correcto en >75% de los casos
- [ ] Nombres de columnas correctos (`carga_maxima_tn`, no inventados)
- [ ] No genera INSERT/UPDATE/DELETE (el validador lo bloquea, pero no debe intentarlo)
- [ ] Tiempo de respuesta < 30 segundos por consulta en CPU
- [ ] El SQL se ejecuta sin errores en PostgreSQL

Si algún criterio falla, ver sección de [solución de problemas](#9-solución-de-problemas-frecuentes).

---

## 9. Solución de problemas frecuentes

### Error: CUDA out of memory

```
RuntimeError: CUDA out of memory. Tried to allocate X GiB
```

**Causa:** El batch es muy grande para la T4.  
**Solución:** En `finetune_qlora.py` reducir:

```python
per_device_train_batch_size = 1    # bajar de 2 a 1
gradient_accumulation_steps = 8    # subir de 4 a 8 (compensa el batch pequeño)
```

---

### Error: No module named 'bitsandbytes'

```
ModuleNotFoundError: No module named 'bitsandbytes'
```

**Solución:**

```python
!pip install bitsandbytes==0.44.1 --quiet
import importlib; importlib.reload(importlib)
```

---

### El modelo genera SQL con columnas incorrectas

**Síntoma:** Genera `WHERE max_load >= 10` en lugar de `WHERE carga_maxima_tn >= 10`.  
**Causa:** El dataset de entrenamiento no tenía suficientes ejemplos con ese campo.  
**Solución:**

1. Añadir más ejemplos con `carga_maxima_tn` en `generate_training_data.py`
2. Regenerar el dataset y re-entrenar

---

### El modelo no usa funciones PostGIS

**Síntoma:** Para consultas de distancia genera `WHERE ...` sin `ST_DWithin`.  
**Causa:** Pocos ejemplos espaciales en el entrenamiento.  
**Solución:** Aumentar el peso de ejemplos espaciales en el dataset regenerando con más combinaciones de vías y distancias.

---

### Colab desconecta a mitad del entrenamiento

**Causa:** Colab gratuito desconecta después de ~90 minutos de inactividad o por uso intensivo.  
**Prevención:**

```python
# Ejecutar en una celda separada para mantener activo Colab
import time
while True:
    time.sleep(60)
    print(".", end="", flush=True)
```

**Si ya desconectó:** El adaptador parcial puede haberse guardado en Drive.
Verifica si existe `/content/drive/MyDrive/geonlq/geonlq-sql-adapter/`.
Si está ahí, el entrenamiento completó al menos hasta el último checkpoint guardado.

---

### El GGUF se genera pero Ollama falla al cargarlo

```
Error: llama runner process has terminated: ...
```

**Causa:** El GGUF puede estar corrupto si la descarga se interrumpió.  
**Solución:** Verificar integridad y re-descargar:

```bash
# En WSL: verificar tamaño mínimo esperado (~800 MB)
ls -lh "/mnt/d/.../modelos_locales/ollama/geonlq-sql-Q4_K_M.gguf"
# Si es menor de 500 MB, está incompleto → re-descargar
```

---

## 10. Referencia de parámetros

### Parámetros de QLoRA (`finetune_qlora.py`)

| Parámetro | Valor por defecto | Descripción |
|-----------|-------------------|-------------|
| `lora_r` | 16 | Rango de las matrices LoRA. Mayor = más capacidad, más VRAM |
| `lora_alpha` | 32 | Escala de las matrices LoRA (generalmente = 2×r) |
| `lora_dropout` | 0.05 | Regularización para evitar overfitting |
| `num_epochs` | 3 | Veces que el modelo ve todo el dataset |
| `per_device_train_batch_size` | 2 | Ejemplos por paso (bajar a 1 si hay OOM) |
| `gradient_accumulation_steps` | 4 | Pasos antes de actualizar pesos |
| `learning_rate` | 2e-4 | Velocidad de aprendizaje |
| `max_seq_length` | 512 | Longitud máxima de tokens por ejemplo |

### Parámetros de generación en Modelfile

| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `temperature` | 0 | Sin aleatoriedad → SQL determinista siempre igual |
| `top_p` | 0.9 | Muestreo nucleus |
| `num_predict` | 512 | Máximo de tokens generados por respuesta |

### Tipos de cuantización GGUF disponibles

| Tipo | Tamaño (~1.5B) | Calidad | Uso recomendado |
|------|---------------|---------|-----------------|
| `Q8_0` | ~1.6 GB | Excelente | Si tienes suficiente RAM |
| `Q4_K_M` | ~900 MB | Muy buena | **Recomendado — balance óptimo** |
| `Q4_0` | ~800 MB | Buena | Si quieres ahorrar más RAM |
| `Q2_K` | ~550 MB | Aceptable | Solo si la RAM es muy limitada |

---

## 11. Checklist completo

### Preparación (en WSL, máquina local)

```
□ Entorno virtual activado: source ~/geonlq/.venv/bin/activate
□ Dataset generado: python generate_training_data.py --count 1500 --split
□ Muestra revisada manualmente: al menos 10 ejemplos verificados
□ Archivos listos para subir a Colab:
  □ modelos_locales/datos/train.jsonl
  □ modelos_locales/datos/eval.jsonl
  □ modelos_locales/scripts/finetune_qlora.py
  □ modelos_locales/scripts/export_to_gguf.sh
```

### Entrenamiento (en Google Colab)

```
□ Runtime configurado con GPU T4
□ Google Drive montado y carpeta /geonlq/ creada
□ Dependencias instaladas (transformers, peft, trl, bitsandbytes)
□ Archivos de datos subidos y copiados a Drive
□ Script de fine-tuning subido
□ Entrenamiento ejecutado (train_loss baja, eval_loss estable)
□ Adaptador guardado en Drive: geonlq-sql-adapter/
□ Exportación GGUF ejecutada
□ GGUF guardado en Drive: geonlq-sql-Q4_K_M.gguf
□ GGUF descargado a Windows (carpeta Descargas)
```

### Despliegue (en WSL, máquina local)

```
□ GGUF copiado a modelos_locales/ollama/
□ ollama create geonlq-sql -f Modelfile ejecutado sin errores
□ ollama list muestra geonlq-sql
□ Prueba directa en Ollama exitosa: ollama run geonlq-sql "..."
□ .env actualizado: LLM_MODEL=geonlq-sql
□ Servicio GeoNLQ reiniciado
□ 4 consultas de prueba ejecutadas y verificadas
□ Criterios de aceptación cumplidos
□ Historial de versiones actualizado en ESCALADO.md
```

---

## Historial de entrenamientos

| Versión | Fecha | Ejemplos (train/eval) | Epochs | Loss final | Notas |
|---------|-------|----------------------|--------|------------|-------|
| v1 | — | — / — | 3 | — | Primer entrenamiento |

*Actualizar esta tabla después de cada entrenamiento.*
