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
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Authentifizierung für Single-User Betrieb
"""
from functools import wraps
from flask import session, redirect, url_for, flash


def auth_required(f):
    """Decorator: Prüft ob User authentifiziert ist"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            flash('Bitte zuerst anmelden')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated
