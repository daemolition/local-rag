# Open Knowledge UI - A privacy-focused, self-hosted RAG system
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
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Version der Anwendung.

Einzige Quelle ist ``pyproject.toml`` (wird von ``scripts/release.py`` gepflegt und
liegt auch im Docker-Image). Fallback: Umgebungsvariable ``APP_VERSION``.
"""

import os
import tomllib
from functools import lru_cache
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
UNKNOWN = "unbekannt"


@lru_cache(maxsize=1)
def get_version() -> str:
    try:
        with PYPROJECT.open("rb") as f:
            return str(tomllib.load(f)["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return os.getenv("APP_VERSION") or UNKNOWN
