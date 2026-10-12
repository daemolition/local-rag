import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app import database_service


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Isolierte SQLite-DB mit Standard-Knowledge; Pfade relativ zu tmp_path."""
    monkeypatch.chdir(tmp_path)
    # init_db_service ist ein Singleton: pro Test zuruecksetzen (nie die echte DB).
    monkeypatch.setattr(database_service, "db_service", None)
    (tmp_path / "data").mkdir()
    # TEST_DATABASE_URL=postgresql+psycopg://... fuehrt die Suite gegen Postgres aus
    # (Schema wird pro Test neu angelegt); sonst SQLite in tmp_path.
    target = os.getenv("TEST_DATABASE_URL") or str(tmp_path / "data" / "app.db")
    if "://" in target and not target.startswith("sqlite"):
        from sqlalchemy import create_engine

        from app.models import Base

        engine = create_engine(target)
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        engine.dispose()
    service = database_service.init_db_service(target)
    service.init_default_data()
    return service


@pytest.fixture(autouse=True)
def silence_phase_logger():
    """Der PhaseLogger erzeugt Records ohne Zeilennummer; pytests Log-Format
    (%(lineno)d) scheitert daran. Fuer Tests abschalten."""
    from app.utils.phase_logger import phase_logger

    phase_logger.logger.disabled = True
    yield
    phase_logger.logger.disabled = False
