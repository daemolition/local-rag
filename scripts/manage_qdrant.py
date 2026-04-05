#!/usr/bin/env python3
"""
Qdrant Management Script

Verwaltung und Migration zwischen lokaler und remote Qdrant-Instanz.

Usage:
    # Status beider Verbindungen prüfen
    uv run python scripts/manage_qdrant.py status

    # Migration lokal → remote (Dry-Run)
    uv run python scripts/manage_qdrant.py migrate --from local --to-remote --dry-run

    # Migration wirklich durchführen
    uv run python scripts/manage_qdrant.py migrate --from local --to-remote

    # Migration remote → lokal  
    uv run python scripts/manage_qdrant.py migrate --from-remote --to local

    # Collection-Info anzeigen
    uv run python scripts/manage_qdrant.py info --target local

    # Mit custom Host/Port
    uv run python scripts/manage_qdrant.py migrate --from local --to-remote --host 192.168.1.100 --port 6333
"""
import argparse
import sys
import time
from pathlib import Path
from typing import Optional

# Füge Projekt-Root zu sys.path hinzu
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from tqdm import tqdm


def create_local_client() -> QdrantClient:
    """Erstellt Client für lokale Qdrant DB."""
    db_path = project_root / "local_qdrant.db"
    return QdrantClient(path=str(db_path))


def create_remote_client(host: str, port: int, api_key: Optional[str] = None) -> QdrantClient:
    """Erstellt Client für remote Qdrant Server."""
    if api_key:
        return QdrantClient(host=host, port=port, api_key=api_key)
    return QdrantClient(host=host, port=port)


def test_connection(client: QdrantClient, name: str) -> tuple[bool, str]:
    """Testet die Verbindung zu einem Qdrant Server."""
    try:
        collections = client.get_collections()
        return True, f"✓ Verbunden. {len(collections.collections)} Collection(s)"
    except Exception as e:
        return False, f"✗ Fehler: {str(e)}"


def get_collection_info(client: QdrantClient, collection_name: str) -> Optional[dict]:
    """Holt Informationen über eine Collection."""
    try:
        collection = client.get_collection(collection_name)
        
        try:
            count = client.count(collection_name)
            points_count = count.count
        except:
            points_count = collection.points_count
        
        return {
            'name': collection_name,
            'points_count': points_count,
            'vectors_count': getattr(collection, 'indexed_vectors_count', collection.points_count),
            'status': str(collection.status),
            'vector_size': collection.config.params.vectors.size if hasattr(collection.config.params, 'vectors') else None,
            'distance': str(collection.config.params.vectors.distance) if hasattr(collection.config.params, 'vectors') else None,
        }
    except Exception as e:
        return None


def migrate_collection(
    source_client: QdrantClient,
    target_client: QdrantClient,
    collection_name: str,
    batch_size: int = 100,
    dry_run: bool = False
) -> tuple[bool, str]:
    """
    Migriert eine Collection von Source zu Target.
    
    Returns:
        tuple: (success: bool, message: str)
    """
    # Source prüfen
    source_info = get_collection_info(source_client, collection_name)
    if not source_info:
        return False, f"Collection '{collection_name}' nicht in Source gefunden"
    
    print(f"\n{'='*60}")
    print(f"Migration: {collection_name}")
    print(f"{'='*60}")
    print(f"Source Points: {source_info['points_count']:,}")
    print(f"Vector Size: {source_info['vector_size']}")
    print(f"Distance: {source_info['distance']}")
    
    if dry_run:
        print(f"\n[DRY-RUN] Würde {source_info['points_count']:,} Punkte migrieren")
        return True, "Dry-Run erfolgreich"
    
    # Target Collection erstellen
    target_exists = False
    try:
        target_client.get_collection(collection_name)
        target_exists = True
        print(f"\n⚠ Collection existiert bereits in Target")
        
        # Prüfen ob gleiche Konfiguration
        target_info = get_collection_info(target_client, collection_name)
        if target_info and target_info['vector_size'] != source_info['vector_size']:
            return False, f"Vector Size mismatch: Source={source_info['vector_size']}, Target={target_info['vector_size']}"
        
        # User fragen
        response = input("Collection überschreiben? (j/N): ")
        if response.lower() != 'j':
            print("Migration abgebrochen")
            return False, "Abgebrochen durch User"
        
        # Löschen und neu erstellen
        target_client.delete_collection(collection_name)
        print("Bestehende Collection gelöscht")
    except:
        pass
    
    # Neue Collection erstellen
    try:
        vectors_config = qdrant_models.VectorParams(
            size=source_info['vector_size'],
            distance=getattr(qdrant_models.Distance, source_info['distance'].upper())
        )
        
        target_client.create_collection(
            collection_name=collection_name,
            vectors_config=vectors_config
        )
        print(f"✓ Collection erstellt")
    except Exception as e:
        return False, f"Fehler beim Erstellen der Collection: {e}"
    
    # Punkte migrieren
    total_points = source_info['points_count']
    migrated = 0
    errors = 0
    
    print(f"\nMigration startet...")
    
    # Scroll durch alle Punkte
    offset = None
    with tqdm(total=total_points, desc="Punkte") as pbar:
        while True:
            try:
                # Batch aus Source holen
                records, offset = source_client.scroll(
                    collection_name=collection_name,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True
                )
                
                if not records:
                    break
                
                # In Target einfügen
                points = [
                    qdrant_models.PointStruct(
                        id=record.id,
                        vector=record.vector,
                        payload=record.payload
                    )
                    for record in records
                ]
                
                target_client.upsert(
                    collection_name=collection_name,
                    points=points
                )
                
                migrated += len(points)
                pbar.update(len(points))
                
                if offset is None:
                    break
                    
            except Exception as e:
                errors += 1
                print(f"\n⚠ Fehler bei Batch: {e}")
                if offset is None:
                    break
                continue
    
    # Validierung
    target_info = get_collection_info(target_client, collection_name)
    if target_info:
        if target_info['points_count'] == source_info['points_count']:
            print(f"\n✓ Migration erfolgreich!")
            print(f"  Migriert: {migrated:,} Punkte")
            return True, f"Migration erfolgreich: {migrated:,} Punkte"
        else:
            print(f"\n⚠ Validierungsfehler!")
            print(f"  Source: {source_info['points_count']:,}")
            print(f"  Target: {target_info['points_count']:,}")
            return False, f"Validierungsfehler: {target_info['points_count']}/{source_info['points_count']}"
    
    return True, f"Migration abgeschlossen: {migrated:,} Punkte"


def cmd_status(args):
    """Zeigt Status beider Verbindungen."""
    print("Qdrant Verbindungsstatus")
    print("=" * 60)
    
    # Lokale Verbindung
    print("\n📁 Lokale Qdrant (./local_qdrant.db):")
    try:
        client = create_local_client()
        success, msg = test_connection(client, "local")
        print(f"  {msg}")
        
        # Collections anzeigen
        try:
            collections = client.get_collections()
            for col in collections.collections:
                info = get_collection_info(client, col.name)
                if info:
                    print(f"    - {info['name']}: {info['points_count']:,} Punkte")
        except Exception as e:
            print(f"  Fehler beim Lesen: {e}")
    except Exception as e:
        print(f"  ✗ Nicht verfügbar: {e}")
    
    # Remote Verbindung
    print(f"\n🌐 Remote Qdrant ({args.host}:{args.port}):")
    try:
        client = create_remote_client(args.host, args.port, args.api_key)
        success, msg = test_connection(client, "remote")
        print(f"  {msg}")
        
        if success:
            try:
                collections = client.get_collections()
                for col in collections.collections:
                    info = get_collection_info(client, col.name)
                    if info:
                        print(f"    - {info['name']}: {info['points_count']:,} Punkte")
            except Exception as e:
                print(f"  Fehler beim Lesen: {e}")
    except Exception as e:
        print(f"  ✗ Nicht verfügbar: {e}")
    
    print("\n" + "=" * 60)


def cmd_migrate(args):
    """Führt Migration durch."""
    print("Qdrant Migration")
    print("=" * 60)
    
    if args.dry_run:
        print("📝 DRY-RUN Modus (keine Änderungen werden vorgenommen)")
    
    # Source und Target bestimmen
    if args.source == "local":
        print("\n📁 Source: Lokale Qdrant")
        source_client = create_local_client()
    else:
        print(f"\n🌐 Source: Remote Qdrant ({args.host}:{args.port})")
        source_client = create_remote_client(args.host, args.port, args.api_key)
    
    # Target
    if args.target == "local":
        print("📁 Target: Lokale Qdrant")
        target_client = create_local_client()
    else:
        print(f"🌐 Target: Remote Qdrant ({args.host}:{args.port})")
        target_client = create_remote_client(args.host, args.port, args.api_key)
    
    # Verbindungen testen
    print("\nVerbindungen testen...")
    src_ok, src_msg = test_connection(source_client, "source")
    tgt_ok, tgt_msg = test_connection(target_client, "target")
    
    print(f"  Source: {src_msg}")
    print(f"  Target: {tgt_msg}")
    
    if not src_ok:
        print("\n✗ Source nicht verfügbar. Abbruch.")
        sys.exit(1)
    if not tgt_ok:
        print("\n✗ Target nicht verfügbar. Abbruch.")
        sys.exit(1)
    
    # Collections bestimmen
    if args.collection:
        collections = [args.collection]
    else:
        try:
            cols = source_client.get_collections()
            collections = [c.name for c in cols.collections]
        except Exception as e:
            print(f"\n✗ Fehler beim Lesen der Collections: {e}")
            sys.exit(1)
    
    if not collections:
        print("\n✗ Keine Collections in Source gefunden.")
        sys.exit(1)
    
    print(f"\nZu migrierende Collections: {', '.join(collections)}")
    
    if not args.dry_run:
        response = input("\nMigration starten? (j/N): ")
        if response.lower() != 'j':
            print("Abgebrochen")
            sys.exit(0)
    
    # Migration durchführen
    success_count = 0
    error_count = 0
    
    for collection_name in collections:
        success, msg = migrate_collection(
            source_client,
            target_client,
            collection_name,
            batch_size=args.batch_size,
            dry_run=args.dry_run
        )
        
        if success:
            success_count += 1
        else:
            error_count += 1
            print(f"✗ Fehler: {msg}")
    
    # Zusammenfassung
    print(f"\n{'='*60}")
    print("Zusammenfassung:")
    print(f"  Erfolgreich: {success_count}")
    print(f"  Fehler: {error_count}")
    if args.dry_run:
        print("\n  (Dry-Run: Keine Änderungen vorgenommen)")
    print("=" * 60)
    
    if error_count > 0:
        sys.exit(1)


def cmd_info(args):
    """Zeigt Collection-Info."""
    print("Collection Information")
    print("=" * 60)
    
    if args.target == "local":
        client = create_local_client()
        print(f"\n📁 Lokale Qdrant:")
    else:
        client = create_remote_client(args.host, args.port, args.api_key)
        print(f"\n🌐 Remote Qdrant ({args.host}:{args.port}):")
    
    # Verbindung testen
    ok, msg = test_connection(client, args.target)
    print(f"  {msg}")
    
    if not ok:
        sys.exit(1)
    
    # Collections anzeigen
    try:
        collections = client.get_collections()
        
        if not collections.collections:
            print("\n  Keine Collections vorhanden")
            return
        
        print(f"\n{'Collection':<20} {'Punkte':>12} {'Status':<15}")
        print("-" * 50)
        
        for col in collections.collections:
            info = get_collection_info(client, col.name)
            if info:
                if 'error' in info:
                    print(f"{col.name:<20} {'ERROR':>12} {info['error'][:15]:<15}")
                else:
                    print(f"{col.name:<20} {info['points_count']:>12,} {info['status']:<15}")
            else:
                print(f"{col.name:<20} {'N/A':>12} {'N/A':<15}")
    
    except Exception as e:
        print(f"\n✗ Fehler: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Qdrant Management Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
    # Status prüfen
    uv run python scripts/manage_qdrant.py status
    
    # Migration (Dry-Run)
    uv run python scripts/manage_qdrant.py migrate --from local --to-remote --dry-run
    
    # Migration durchführen
    uv run python scripts/manage_qdrant.py migrate --from local --to-remote
    
    # Nur spezifische Collection
    uv run python scripts/manage_qdrant.py migrate --from local --to-remote --collection my_docs
    
    # Mit custom Host
    uv run python scripts/manage_qdrant.py migrate --from local --to-remote --host 192.168.1.100 --port 6333
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Befehl')
    
    # Status Command
    status_parser = subparsers.add_parser('status', help='Zeigt Verbindungsstatus')
    status_parser.add_argument('--host', default='localhost', help='Remote Host (default: localhost)')
    status_parser.add_argument('--port', type=int, default=6333, help='Remote Port (default: 6333)')
    status_parser.add_argument('--api-key', help='API Key für gesicherte Qdrant')
    
    # Migrate Command
    migrate_parser = subparsers.add_parser('migrate', help='Migriert Collections')
    migrate_parser.add_argument('--from', dest='source', choices=['local', 'remote'], required=True,
                               help='Source-Typ')
    migrate_parser.add_argument('--to', dest='target', choices=['local', 'remote'], required=True,
                               help='Target-Typ')
    migrate_parser.add_argument('--collection', help='Nur diese Collection migrieren')
    migrate_parser.add_argument('--batch-size', type=int, default=100, help='Batch-Größe (default: 100)')
    migrate_parser.add_argument('--dry-run', action='store_true', help='Nur simulieren, keine Änderungen')
    migrate_parser.add_argument('--host', default='localhost', help='Remote Host (default: localhost)')
    migrate_parser.add_argument('--port', type=int, default=6333, help='Remote Port (default: 6333)')
    migrate_parser.add_argument('--api-key', help='API Key für gesicherte Qdrant')
    
    # Info Command
    info_parser = subparsers.add_parser('info', help='Zeigt Collection-Info')
    info_parser.add_argument('--target', choices=['local', 'remote'], required=True,
                           help='Welche Qdrant-Instanz')
    info_parser.add_argument('--host', default='localhost', help='Remote Host')
    info_parser.add_argument('--port', type=int, default=6333, help='Remote Port')
    info_parser.add_argument('--api-key', help='API Key')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Befehl ausführen
    if args.command == 'status':
        cmd_status(args)
    elif args.command == 'migrate':
        cmd_migrate(args)
    elif args.command == 'info':
        cmd_info(args)


if __name__ == '__main__':
    main()
