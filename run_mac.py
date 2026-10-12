#!/usr/bin/env python3

# Local Document RAG - A privacy-focused, local RAG system
# Copyright (C) 2026 Christopher Abanilla
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#

"""
macOS Entry Point (App nativ, Hilfsdienste in Docker)
- Gunicorn auf 127.0.0.1:5000
- Hilfsdienste (Postgres, Qdrant, SearXNG, entityguard, Parakeet) in Docker, siehe docker-compose.mac.yml
- Embedding, Reranking und Docling rechnen auf Apple Silicon ueber Metal (MPS);
  ONNX-Modelle nutzen CoreML. Mit RAG_DEVICE=cpu abschaltbar.

Docker auf dem Mac laeuft in einer Linux-VM ohne Zugriff auf die GPU: nur die App laeuft
deshalb nativ, alles andere bleibt in Docker.

Usage:
    python run_mac.py              # Docker-Dienste starten + App
    python run_mac.py --no-docker  # Nur die App (Dienste laufen schon bzw. woanders)
"""

import os
import subprocess
import sys
import time

COMPOSE_FILE = "docker-compose.mac.yml"

# Die Hilfsdienste laufen in Docker (Ports auf localhost); die App erreicht sie darueber.
# Gilt nur fuer eine frische Datenbank, danach stehen die Werte in den Einstellungen.
SERVICE_DEFAULTS = {
    "DATABASE_URL": "postgresql+psycopg://rag:rag@localhost:5432/rag",
    "QDRANT_HOST": "localhost",
    "SEARCH_SEARXNG_URL": "http://localhost:8081",
    "PII_FILTER_URL": "http://localhost:8082/api/v1/sanitize",
    "STT_BASEURL": "http://localhost:5001/v1",
}


def wait_for_postgres(timeout: int = 60) -> bool:
    """Wartet, bis die Datenbank Verbindungen annimmt (sonst scheitert die Migration)."""
    for _ in range(timeout):
        ready = subprocess.run(
            ["docker", "compose", "-f", COMPOSE_FILE, "exec", "-T", "postgres", "pg_isready", "-q"],
            capture_output=True,
        )
        if ready.returncode == 0:
            time.sleep(1)  # Qdrant braucht ebenfalls einen Moment
            return True
        time.sleep(1)
    print("❌ Postgres wurde nicht rechtzeitig bereit.")
    return False


def start_services() -> bool:
    print("🐳 Starte Hilfsdienste (Postgres, Qdrant, SearXNG, entityguard, Parakeet) in Docker...")
    try:
        result = subprocess.run(["docker", "compose", "-f", COMPOSE_FILE, "up", "-d"])
    except FileNotFoundError:
        print("❌ Docker nicht gefunden. Docker Desktop installieren oder --no-docker nutzen.")
        return False
    if result.returncode != 0:
        print("❌ docker compose ist fehlgeschlagen (siehe oben).")
        return False
    return wait_for_postgres()


def main():
    print("=" * 50)
    print(" Local Document RAG - macOS Mode")
    print("=" * 50)
    for key, value in SERVICE_DEFAULTS.items():
        os.environ.setdefault(key, value)
    if "--no-docker" not in sys.argv[1:] and not start_services():
        sys.exit(1)

    print("📊 Alembic Migration...")
    result = subprocess.run(["alembic", "upgrade", "head"], capture_output=True, text=True)
    print("✅ Migration erfolgreich" if result.returncode == 0 else f"⚠️  Migration Fehler:\n{result.stderr}")

    print("🚀 Starte Gunicorn auf http://127.0.0.1:5000")
    # Ein Worker (In-Memory-State), Threads fuer parallele Requests, siehe run_linux.py.
    # Auf dem Mac erlaubt PyTorch/MPS kein fork() nach dem Laden der Modelle: kein --preload.
    os.system(
        "gunicorn -w 1 --threads 4 -k gthread -b 127.0.0.1:5000 --timeout 240 'app:create_app(preload=True)'"
    )


if __name__ == "__main__":
    main()
