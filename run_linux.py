#!/usr/bin/env python3
"""
Linux Entry Point
- Gunicorn auf 0.0.0.0:5000 (Docker)
- Qdrant separat (docker-compose)
- Alembic Migration automatisch

Usage:
    python run_linux.py              # Normaler Start (mit Alembic)
"""

import subprocess
import sys


def main():
    print("=" * 50)
    print("🐧 Local Document RAG - Linux Mode")
    print("=" * 50)
    print()
    print("   Gunicorn: http://0.0.0.0:5000")
    print("   Qdrant: Separat (docker-compose)")
    print()
    
    # Alembic Migration (immer ausführen)
    print("📊 Alembic Migration...")
    result = subprocess.run(["alembic", "upgrade", "head"], capture_output=True, text=True)
    if result.returncode == 0:
        print("✅ Migration erfolgreich")
    else:
        print("⚠️  Migration Fehler:")
        print(result.stderr)
    print()
    
    print("=" * 50)
    print("🚀 Starte Gunicorn...")
    print("=" * 50)
    print()
    
    # Gunicorn starten
    import os
    os.system("gunicorn -w 1 -b 0.0.0.0:5000 'app:create_app()'")


if __name__ == "__main__":
    main()
