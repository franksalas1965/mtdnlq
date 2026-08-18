#!/usr/bin/env bash
# Genera dist/: imagen Docker + código src/ para despliegue con volumen.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/dist"
IMAGE="${GEONLQ_IMAGE:-geonlq:latest}"
OUT="$DIST/geonlq-latest.tar.gz"

mkdir -p "$DIST"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Imagen $IMAGE no encontrada. Construye antes:"
  echo "  cd \"$ROOT\" && docker compose -f docker-compose.external-db.yml build"
  exit 1
fi

echo "==> Sincronizando src/ -> dist/src/"
rsync -a --delete \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  "$ROOT/src/" "$DIST/src/"

echo "==> Exportando $IMAGE -> $OUT"
docker save "$IMAGE" | gzip > "$OUT"
ls -lh "$OUT"
du -sh "$DIST/src"
echo "Listo. Lleva toda la carpeta dist/ al servidor (imagen + src/)."
