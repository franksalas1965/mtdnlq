# Configuración LLM — Ollama local, Ollama Cloud, CPU/GPU

El **plugin QGIS** no guarda claves LLM: se conecta a MTD-NLQ y el **servidor** llama al modelo.  
Configure el `.env` del servicio y reinicie uvicorn.

> **Nota sobre geo-ai-query-system:** ese proyecto usa **OpenRouter + DeepSeek**, no Ollama Cloud.
> MTD-NLQ soporta **Ollama local/cloud** nativamente y también **OpenAI/Anthropic** vía API key.

---

## Modos Ollama

| Modo | `OLLAMA_MODE` | URL | Autenticación |
|------|---------------|-----|---------------|
| Local (CPU/GPU) | `local` | `OLLAMA_BASE_URL` (default `http://localhost:11434`) | Ninguna |
| Ollama Cloud | `cloud` | `https://ollama.com` | `OLLAMA_API_KEY` (Bearer) |

Documentación oficial: [Ollama Cloud](https://docs.ollama.com/cloud), [Authentication](https://docs.ollama.com/api/authentication).

---

## Ollama Cloud (mejor rendimiento sin GPU local)

1. Cree una API key en https://ollama.com/settings/keys  
2. En `.env` del servidor MTD-NLQ:

```env
LLM_PROVIDER=ollama
OLLAMA_MODE=cloud
OLLAMA_API_KEY=su_clave_aqui
OLLAMA_CLOUD_BASE_URL=https://ollama.com
# LLM_MODEL opcional: por defecto gemma4:31b al activar cloud
# Alternativa más potente (más cuota): LLM_MODEL=qwen3.5:397b
OLLAMA_TIMEOUT_SECONDS=120
MAX_CONCURRENT_LLM_JOBS=2
```

3. Reinicie MTD-NLQ.

Verifique:

```powershell
Invoke-RestMethod http://localhost:8001/api/v1/config/llm
```

Debe mostrar `"ollama_mode": "cloud"` y `"ollama_api_key_configured": true`.

---

## Ollama local — CPU vs GPU

```env
LLM_PROVIDER=ollama
OLLAMA_MODE=local
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=qwen2.5-coder:7b

# Dispositivo: auto | cpu | gpu
OLLAMA_DEVICE=gpu

# Solo local — capas en GPU (-1 = todas, 0 = solo CPU)
OLLAMA_NUM_GPU=-1

# Hilos CPU (0 = automático)
OLLAMA_NUM_THREAD=0
```

| `OLLAMA_DEVICE` | Efecto |
|-----------------|--------|
| `cpu` | Fuerza `num_gpu=0` (solo CPU) |
| `gpu` | Fuerza GPU (`num_gpu=-1` o valor de `OLLAMA_NUM_GPU`) |
| `auto` | Ollama elige; use `OLLAMA_NUM_GPU` solo si quiere fijar capas |

**Servidor con GPU NVIDIA:** instale drivers + Ollama con soporte CUDA, ponga `OLLAMA_DEVICE=gpu` y reinicie el servicio MTD-NLQ (no hace falta cambiar código).

**Sin GPU:** `OLLAMA_DEVICE=cpu` o use **Ollama Cloud**.

---

## Comparativa rápida

| Escenario | Configuración recomendada |
|-----------|---------------------------|
| Portátil / pruebas | `local` + `cpu` + modelo pequeño |
| Servidor con GPU | `local` + `gpu` + `qwen2.5-coder:7b` |
| Producción sin GPU aún | `cloud` + `OLLAMA_API_KEY` |
| Máxima calidad SQL | `cloud` + `qwen3.5:397b` o `kimi-k2.7-code` |
| Pruebas cloud (free tier) | `cloud` + default `gemma4:31b` (automático) |

---

## Modelo por defecto en Ollama Cloud

Si pone `OLLAMA_MODE=cloud` y **no** define `LLM_MODEL` (o deja un modelo pensado para local como `qwen2.5-coder:7b`), MTD-NLQ usa **`gemma4:31b`** automáticamente.

| Modelo cloud | Uso en free tier | Contexto | Por qué |
|--------------|------------------|----------|---------|
| **`gemma4:31b`** *(default)* | Bajo | 256K | Buen equilibrio código/SQL + cuota; encaja el esquema MTD grande |
| `qwen3.5:397b` | Medio | 256K | Mejor razonamiento y código; consume más cuota |
| `kimi-k2.7-code` | Alto | 256K | Especializado en código; reservar para producción |
| `gpt-oss:120b` | Medio | — | Generalista; menos orientado a SQL |

Catálogo actual: [ollama.com/search?c=cloud](https://ollama.com/search?c=cloud).

Para fijar otro modelo explícitamente:

```env
OLLAMA_MODE=cloud
LLM_MODEL=qwen3.5:397b
```

---

## Ver desde QGIS

**Configuración → Probar conexión** muestra BD y modelo.  
El bloque **Motor LLM (servidor)** refleja `GET /api/v1/health` → campo `llm`.

---

## OpenAI / Anthropic (alternativa)

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...
```

No usa `OLLAMA_*`.

---

## Variables completas Ollama

| Variable | Default | Descripción |
|----------|---------|-------------|
| `OLLAMA_MODE` | `local` | `local` \| `cloud` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama local |
| `OLLAMA_CLOUD_BASE_URL` | `https://ollama.com` | API cloud |
| `OLLAMA_API_KEY` | *(vacío)* | Obligatorio en cloud |
| `OLLAMA_DEVICE` | `auto` | `auto` \| `cpu` \| `gpu` (solo local) |
| `OLLAMA_NUM_GPU` | `-1` | Capas GPU (-1=todas, 0=CPU) |
| `OLLAMA_NUM_THREAD` | `0` | Hilos CPU (0=auto) |
| `OLLAMA_TIMEOUT_SECONDS` | `180` | Timeout por inferencia |
| `LLM_MODEL` | — | Modelo Ollama; en cloud sin valor explícito → `gemma4:31b` |

---

## Endpoints API

| Ruta | Descripción |
|------|-------------|
| `GET /api/v1/config/llm` | Config LLM activa (sin secretos) |
| `GET /api/v1/health` | Incluye campo `llm` |
