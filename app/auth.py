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

"""
Authentifizierung und Rollenpruefung.

Die Flask-Session speichert nur ``user_id``. Benutzer und Rolle werden pro
Request aus der DB geladen, damit Aenderungen (Deaktivieren, Rollenwechsel)
sofort wirken.
"""

from functools import wraps

from flask import flash, g, jsonify, redirect, session, url_for

from app.users import get_user, role_at_least


def current_user() -> dict | None:
    """Angemeldeter, aktiver Benutzer des Requests oder ``None`` (pro Request gecacht)."""
    if "current_user" in g:
        return g.current_user
    user = None
    user_id = session.get("user_id")
    if user_id is not None:
        user = get_user(user_id)
        if user is None or not user["is_active"]:
            session.pop("user_id", None)
            user = None
    g.current_user = user
    return user


def auth_required(f):
    """Decorator: Prüft ob User authentifiziert ist"""

    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user() is None:
            flash("Bitte zuerst anmelden")
            return redirect(url_for("main.login"))
        return f(*args, **kwargs)

    return decorated


def auth_required_api(f):
    """Wie auth_required, aber für JSON-APIs: liefert 401 statt Redirect."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user() is None:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        return f(*args, **kwargs)

    return decorated


def require_role(role: str):
    """Decorator fuer JSON-APIs: 401 ohne Anmeldung, 403 bei zu niedriger Rolle.

    ``editor`` erlaubt auch ``admin``.
    """

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify({"error": "Nicht authentifiziert"}), 401
            if not role_at_least(user["role"], role):
                return jsonify({"error": "Keine Berechtigung"}), 403
            return f(*args, **kwargs)

        return decorated

    return decorator
