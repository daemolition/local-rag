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
WebSocket-Proxy: Browser <-> Parakeet-Streaming-ASR-Server.

Flask hat kein natives WebSocket. flask-sock (simple-websocket) stellt die
Browser-Seite bereit; pro Browser-Verbindung wird hier eine eigene
synchrone websocket-client-Verbindung zum internen Parakeet-Service
(`/v1/audio/stream`, siehe parakeet/main.py) geöffnet und in beide
Richtungen durchgereicht:
  * Binäre Float32-PCM-Frames vom Browser -> Parakeet,
  * JSON-Nachrichten (`partial`/`committed`/`final`/`error`) von
    Parakeet -> Browser,
  * Text-Frame `{"event": "stop"}` vom Browser -> Parakeet, danach wird auf
    die abschließende `final`-Nachricht gewartet, bevor beide Seiten
    geschlossen werden.
"""

import json
import logging
import threading
import urllib.parse

import websocket
from flask import session
from flask_sock import Sock
from simple_websocket import ConnectionClosed

from app.database_service import get_db_service
from app.settings_service import SettingsService

logger = logging.getLogger(__name__)

sock = Sock()

_STOP_JOIN_TIMEOUT_S = 15.0


def _build_stream_url(base_url: str) -> str:
    """Wandelt STT_BASEURL (z.B. http://parakeet:5001/v1) in die Parakeet-WS-URL um.

    Gleiche Umwandlung wie im openDox-`ParakeetStreamBackend`-Client:
    Schema auf ws/wss umschreiben, Streaming-Pfad anhängen.
    """
    parsed = urllib.parse.urlparse(base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path or ""
    if not path.endswith("/audio/stream"):
        path = path.rstrip("/") + "/audio/stream"
    return urllib.parse.urlunparse((scheme, parsed.netloc, path, "", "", ""))


@sock.route("/ws/stt-stream")
def stt_stream(ws):
    """Relay: Live-PCM-Audio vom Browser an Parakeet, Transkripte zurückstreamen."""
    if not session.get("authenticated"):
        ws.close()
        return

    db = get_db_service()
    settings = SettingsService(db.get_session())
    base_url = settings.get("STT_BASEURL", "http://parakeet:5001/v1")
    stream_url = _build_stream_url(base_url)

    try:
        upstream = websocket.create_connection(stream_url, timeout=10)
    except Exception as e:
        logger.warning("STT-Stream: Verbindung zu Parakeet fehlgeschlagen: %s", e)
        try:
            ws.send(json.dumps({"error": f"STT-Server nicht erreichbar: {e}"}))
        except ConnectionClosed:
            pass
        return

    stop_event = threading.Event()

    def relay_from_upstream():
        """Liest Nachrichten von Parakeet und reicht sie an den Browser weiter."""
        try:
            while not stop_event.is_set():
                msg = upstream.recv()
                if msg is None or msg == "":
                    break
                try:
                    ws.send(msg)
                except ConnectionClosed:
                    break

                is_final_or_error = False
                if isinstance(msg, str):
                    try:
                        parsed = json.loads(msg)
                        is_final_or_error = "final" in parsed or "error" in parsed
                    except (json.JSONDecodeError, TypeError):
                        pass
                if is_final_or_error:
                    break
        except Exception as e:
            logger.warning("STT-Stream: Upstream-Relay-Fehler: %s", e)
        finally:
            stop_event.set()

    reader_thread = threading.Thread(target=relay_from_upstream, daemon=True)
    reader_thread.start()

    try:
        while not stop_event.is_set():
            try:
                data = ws.receive()
            except ConnectionClosed:
                break
            if data is None:
                continue
            try:
                if isinstance(data, (bytes, bytearray)):
                    upstream.send_binary(bytes(data))
                else:
                    upstream.send(data)
                    if "stop" in data.lower():
                        reader_thread.join(timeout=_STOP_JOIN_TIMEOUT_S)
                        break
            except Exception as e:
                logger.warning(
                    "STT-Stream: Weiterleitung an Parakeet fehlgeschlagen: %s", e
                )
                break
    finally:
        stop_event.set()
        try:
            upstream.close()
        except Exception:
            pass
