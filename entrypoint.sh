#!/bin/bash
set -e

echo "Open Knowledge UI - Docker"
echo "================================"

# Beim Start als root (Image-Default): die Daten- und Cache-Verzeichnisse dem App-Konto
# uebergeben — bestehende Volumes (app-data, hf-cache, fastembed-cache) gehoeren root und
# muessen einmalig uebernommen werden — und auf uid 1000 / gid 0 abgeben. Bestehende Subdirs
# bleiben ueber die Gruppe (0) beschreibbar; neue Volumes gehen direkt als app:0 an den Start.
if [ "$(id -u)" = "0" ]; then
  echo "Uebergebe /app/data und /app/.cache an das App-Konto (uid 1000)..."
  chown -R 1000:0 /app/data /app/.cache
  exec gosu 1000 "$@"
fi

# Alembic Migration
echo "Running database migrations..."
alembic upgrade head

echo "Setup complete"
echo ""

exec "$@"