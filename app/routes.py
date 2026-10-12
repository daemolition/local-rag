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

import asyncio
import io
import json
import re
import logging
import os
import queue
import threading

import openai
from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)

from app import resources_ready, wait_for_resources
from app.tools.web_access import build_web_search_tool, pii_client
from app.access import accessible_knowledge_ids, can_use_model
from app.auth import auth_required_api, current_user
from app.users import LoginThrottledError, authenticate
from app.database_service import get_db_service
from app.llm.registry import ModelUnavailableError, get_agent, resolve_model
from app.retrieval import RetrievalScope, set_scope
from app.settings_service import SettingsService
from app.utils.phase_logger import Phase, phase_logger

bp = Blueprint("main", __name__)
logger = logging.getLogger(__name__)

_STATIC_DIR = None


def serve_spa():
    """Liefert die gebaute React-SPA (app/static/index.html).

    Der Vite-Build schreibt direkt nach ``app/static/`` (siehe
    ``frontend/vite.config.ts``); Flask serviert dieses Verzeichnis unter
    ``/static/...``. Fällt mit einer klaren Meldung zurück, falls das Frontend
    noch nicht gebaut wurde (``cd frontend && npm run build``)."""
    global _STATIC_DIR
    if _STATIC_DIR is None:
        _STATIC_DIR = os.path.join(current_app.root_path, "static")

    index_path = os.path.join(_STATIC_DIR, "index.html")
    if not os.path.isfile(index_path):
        return (
            (
                "<h1>Frontend nicht gebaut</h1>"
                "<p>Bitte zuerst ausführen: <code>cd frontend &amp;&amp; npm install "
                "&amp;&amp; npm run build</code></p>"
            ),
            503,
        )

    # Server-seitigen Theme-Default (UI_THEME) in die SPA-Index einbetten,
    # damit index.html vor dem ersten Paint den richtigen Fallback hat.
    try:
        settings = SettingsService(get_db_service().get_session())
        ui_theme = settings.get("UI_THEME", "system") or "system"
    except Exception:
        ui_theme = "system"

    with open(index_path, encoding="utf-8") as fh:
        html = fh.read()
    html = html.replace("__RAG_UI_THEME__", ui_theme)
    return Response(html, mimetype="text/html")


# Globale Cancel-Events für laufende Chat-Streams, keyed by session_id.
_cancel_events = {}
_cancel_events_lock = threading.Lock()


def _get_cancel_event(session_id):
    with _cancel_events_lock:
        if session_id not in _cancel_events:
            _cancel_events[session_id] = threading.Event()
        return _cancel_events[session_id]


def _set_cancelled(session_id):
    with _cancel_events_lock:
        event = _cancel_events.get(session_id)
        if event is None:
            event = threading.Event()
            event.set()
            _cancel_events[session_id] = event
        else:
            event.set()


def _clear_cancelled(session_id):
    with _cancel_events_lock:
        event = _cancel_events.get(session_id)
        if event is not None:
            event.clear()


# === Session Management API ===


@bp.route("/api/sessions", methods=["GET"])
@auth_required_api
def get_sessions():
    """List all sessions"""
    db = get_db_service()
    sessions = db.list_sessions(user_id=current_user()["id"])

    result = []
    for sess in sessions:
        result.append(
            {
                "id": sess.id,
                "title": sess.title,
                "created_at": sess.created_at.isoformat() if sess.created_at else None,
                "updated_at": sess.updated_at.isoformat() if sess.updated_at else None,
            }
        )

    return jsonify(result)


@bp.route("/api/sessions", methods=["POST"])
@auth_required_api
def new_session():
    """Create a new session"""
    db = get_db_service()
    new_sess = db.create_session(user_id=current_user()["id"])

    return jsonify(
        {
            "id": new_sess.id,
            "title": new_sess.title,
            "created_at": new_sess.created_at.isoformat()
            if new_sess.created_at
            else None,
            "updated_at": new_sess.updated_at.isoformat()
            if new_sess.updated_at
            else None,
        }
    )


@bp.route("/api/sessions/<session_id>", methods=["GET"])
@auth_required_api
def get_session_messages(session_id):
    """Get session with messages"""
    db = get_db_service()
    sess = db.get_chat_session(session_id, user_id=current_user()["id"])

    if not sess:
        return jsonify({"error": "Session nicht gefunden"}), 404

    messages = db.get_messages(session_id)

    message_dicts = []
    for msg in messages:
        message_dicts.append(
            {
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
        )

    return jsonify(
        {
            "id": sess.id,
            "title": sess.title,
            "created_at": sess.created_at.isoformat() if sess.created_at else None,
            "updated_at": sess.updated_at.isoformat() if sess.updated_at else None,
            "messages": message_dicts,
        }
    )


@bp.route("/api/sessions/<session_id>", methods=["DELETE"])
@auth_required_api
def delete_session_route(session_id):
    """Delete a session"""
    db = get_db_service()
    deleted = db.delete_session(session_id, user_id=current_user()["id"])

    if not deleted:
        return jsonify({"error": "Session nicht gefunden"}), 404

    from app.attachments import cleanup_session_attachments

    cleanup_session_attachments(session_id, current_app.extensions.get("client"))

    return jsonify({"success": True})


@bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint for Docker (Liveness). ready=False waehrend
    die Embedding-Modelle im Hintergrund geladen werden."""
    from app.version import get_version

    return {
        "status": "healthy",
        "ready": resources_ready(),
        "version": get_version(),
    }, 200


@bp.route("/api/ingestion-status", methods=["GET"])
@auth_required_api
def ingestion_status():
    """Geteilter Ingestion-Status fuer den Navbar-Indikator per Polling."""
    return jsonify(current_app.extensions["ingestion_status"])


@bp.route("/", methods=["GET"])
def index():
    # Die React-SPA übernimmt das Routing (Chat unter '/'). Der Login-Status
    # wird clientseitig über /api/auth/me geprüft.
    return serve_spa()


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            user = authenticate(
                request.form.get("username", ""),
                request.form.get("password", ""),
                client_ip=request.remote_addr,
            )
        except LoginThrottledError:
            user = None
            flash("Zu viele Fehlversuche. Bitte später erneut versuchen.")
        if user:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("main.index"))

        flash("Benutzername oder Passwort falsch")

    return serve_spa()


@bp.route("/logout", methods=["GET"])
def logout():
    session.clear()
    return redirect(url_for("main.login"))


@bp.route("/history/<session_id>", methods=["GET"])
@auth_required_api
def history(session_id):
    db = get_db_service()
    sess = db.get_chat_session(session_id, user_id=current_user()["id"])

    if not sess:
        return {"error": "Session nicht gefunden"}, 404

    messages = db.get_messages(session_id)

    message_dicts = []
    for msg in messages:
        message_dicts.append(
            {
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
        )

    return {"history": message_dicts}


@bp.route("/chat", methods=["POST"])
@auth_required_api
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    session_id = data.get("session_id")
    # None = alle Knowledge-Bereiche; Liste = nur diese (leer = keiner).
    knowledge_ids = data.get("knowledge_ids")

    if not user_message:
        return Response(
            'data: {"error": "Keine Nachricht"}\n\n', mimetype="text/event-stream"
        )

    db = get_db_service()
    final_session_id = session_id
    sess = None

    if session_id:
        sess = db.get_chat_session(session_id, user_id=current_user()["id"])
        if not sess:
            return Response(
                'data: {"error": "Ungültige Session"}\n\n', mimetype="text/event-stream"
            )
    else:
        new_sess = db.create_session(user_id=current_user()["id"])
        final_session_id = new_sess.id
        sess = new_sess

    if not sess.title:
        title = user_message[:50] + ("..." if len(user_message) > 50 else "")
        db.update_session_title(final_session_id, title)

    phase_logger.log_phase(Phase.USER_INPUT, f"User-Query: {user_message[:100]}...")

    if not resources_ready():
        try:
            ready = wait_for_resources(timeout=180)
        except RuntimeError as e:
            return Response(
                f'data: {{"error": "{e}"}}\n\n', mimetype="text/event-stream"
            )
        if not ready:
            return Response(
                'data: {"error": "RAG-System wird noch initialisiert '
                "(Embedding-Modell lädt). Bitte in wenigen Sekunden "
                'erneut versuchen."}\n\n',
                mimetype="text/event-stream",
            )

    # Modell des Requests (oder Standardmodell) -> eigener Agent mit Prompt,
    # Parametern und ggf. angehaengtem Knowledge. Ohne Modell gibt es keinen Chat.
    model_ref = data.get("model")
    user = current_user()
    # Knowledge, das das Modell selbst mitbringt (vom Admin kuratiert): wer das
    # Modell nutzen darf, darf es durchsuchen. Sonst gelten die Rechte des Nutzers.
    model_locked = False
    resolved = None
    try:
        resolved = resolve_model(model_ref)
        if not can_use_model(user, resolved.ref):
            return Response(
                'data: {"error": "Kein Zugriff auf dieses Modell."}\n\n',
                mimetype="text/event-stream",
            )
        tools = list(current_app.extensions["agent_tools"])
        # Websuche nur, wenn das Modell sie hat UND SearXNG samt PII-Filter eingerichtet sind.
        if resolved.web_search:
            web_tool = build_web_search_tool()
            if web_tool:
                tools.append(web_tool)
        agent = get_agent(resolved, tools)
        if resolved.knowledge_ids:
            knowledge_ids = list(resolved.knowledge_ids)
            model_locked = True
    except ModelUnavailableError as e:
        message = (
            f"{e} Bitte in der Administration eine Verbindung anlegen und ein Standardmodell wählen."
            if not model_ref
            else str(e)
        )
        return Response(
            f"data: {json.dumps({'error': message})}\n\n",
            mimetype="text/event-stream",
        )

    messages = db.get_messages(final_session_id, limit=10)
    message_list = []

    for msg in messages[-10:]:
        role = "user" if msg.role == "user" else "assistant"
        # Quellenblock der Anzeige gehoert nicht in den Verlauf fuers Modell
        content = re.sub(r"\n*<sources>.*?</sources>\s*$", "", msg.content, flags=re.S)
        message_list.append({"role": role, "content": content})

    # User-Nachricht durch PII-Filter schicken (vor LLM-Call)
    pii_filter = pii_client()  # None, wenn nicht eingerichtet oder abgeschaltet
    pii_filter_enabled = pii_filter is not None

    filtered_user_message = user_message
    pii_mapping = []  # Mapping für spätere Demaskierung der Antwort speichern

    if pii_filter and pii_filter_enabled:
        try:
            from app.utils.pii_filter_client import PIIFilterResult

            result: PIIFilterResult = pii_filter.filter_text(user_message)
            if result.error:
                logger.warning(
                    f"PII-Filter Fehler: {result.error} - verwende Original-Nachricht"
                )
            elif result.filtered != result.original:
                logger.info(f"PII-Filter: {len(result.mapping)} Entitäten maskiert")
                filtered_user_message = result.filtered
                pii_mapping = result.mapping  # Mapping für Demaskierung merken
        except Exception as e:
            logger.warning(f"PII-Filter Exception: {e} - verwende Original-Nachricht")

    # Hinweis auf Chat-Anhaenge (nur fuer den Agent, wird nicht gespeichert),
    # damit er die Dokumentsuche auch tatsaechlich darauf anwendet.
    agent_user_message = filtered_user_message
    attached = db.list_session_attachments(final_session_id, status="ready")
    if attached:
        names = ", ".join(f"„{a.filename}“" for a in attached)
        agent_user_message += (
            f"\n\n[Hinweis: Der Nutzer hat in diesem Chat folgende Dateien "
            f"angehängt: {names}. Ihr Inhalt ist über document_search_tool "
            f"durchsuchbar.]"
        )

    message_list.append({"role": "user", "content": agent_user_message})

    logger.info(f"[DEBUG] Messages an Agent: {len(message_list)} Nachrichten")

    input_data = {"messages": message_list}

    # Durchsuchte Collections dieses Requests: gewaehlte Knowledge-Bereiche plus
    # (falls vorhanden) die Anhaenge dieser Session.
    from app.knowledge import list_knowledge

    all_knowledge = list_knowledge()
    if not model_locked:
        # Nie Collections aus dem Request ungeprueft uebernehmen.
        readable = accessible_knowledge_ids(user, "read")
        all_knowledge = [k for k in all_knowledge if k["id"] in readable]
    if knowledge_ids is not None:
        wanted = {int(i) for i in knowledge_ids if str(i).lstrip("-").isdigit()}
        all_knowledge = [k for k in all_knowledge if k["id"] in wanted]
    from app.ingest.index_doc import index_path, inline_hint
    from app.knowledge import knowledge_paths
    from app.rag import model_settings
    from app.rag.helper import make_helper
    from app.rag.profiles import config_for_knowledge

    scope = RetrievalScope(
        user_id=user["id"],
        collections=tuple(k["collection_name"] for k in all_knowledge),
        session_id=final_session_id,
        # Jedes Knowledge sucht mit seinem Retrieval-Profil (sonst Standardprofil).
        profiles=tuple((k["collection_name"], config_for_knowledge(k)) for k in all_knowledge),
        helper=make_helper(resolved, user),
        # pandas-Tools sehen nur die strukturierten Dateien dieser Knowledge-Bereiche
        data_dirs=tuple(
            (paths.name_prefix, str(paths.data_dir))
            for paths in (knowledge_paths(k) for k in all_knowledge)
        ),
        indexes=tuple((k["name"], str(index_path(knowledge_paths(k)))) for k in all_knowledge),
        # fremde Vektorspeicher: Konfiguration (inkl. Key, bleibt im Prozess) je Knowledge
        externals=tuple(
            (k["collection_name"], k["source_config"])
            for k in all_knowledge
            if k.get("kind") == "external" and k.get("source_config")
        ),
        # jedes Knowledge wird mit dem Modell abgefragt, mit dem es indexiert wurde
        specs=tuple(
            (k["collection_name"], json.dumps(model_settings.knowledge_spec(k).to_dict()))
            for k in all_knowledge
        ),
    )
    # Kleines Inhaltsverzeichnis gleich mitgeben ("zuerst lesen"), grosses nur per Werkzeug.
    hint = inline_hint(scope.indexes)
    if hint:
        message_list[-1]["content"] += hint

    def generate():
        result_queue = queue.Queue()
        full_response = ""
        full_reasoning = ""
        tool_calls = []
        cancel_event = _get_cancel_event(final_session_id)
        cancel_event.clear()

        # Mapping für Demaskierung in Closure verfügbar machen
        demask_context = {"mapping": pii_mapping}

        async def run_agent_async():
            nonlocal full_response
            nonlocal full_reasoning
            sources_sent = 0
            try:
                phase_logger.log_phase(Phase.AGENT_START, "Agent-Stream gestartet")
                # Scope im Kontext der Agent-Loop setzen; asyncio und die
                # LangChain-Executors reichen ihn an die Tool-Aufrufe weiter.
                set_scope(scope)

                async for event in agent.astream_events(input_data, version="v2"):
                    if cancel_event.is_set():
                        result_queue.put(("cancelled", None))
                        break

                    kind = event.get("event")

                    if kind == "on_chat_model_stream":
                        chunk = event["data"]["chunk"]
                        content = chunk.content

                        reasoning = None
                        if (
                            hasattr(chunk, "additional_kwargs")
                            and chunk.additional_kwargs
                        ):
                            reasoning = chunk.additional_kwargs.get("reasoning_content")

                        if content:
                            full_response += content
                            result_queue.put(("token", content))

                        if reasoning:
                            full_reasoning += reasoning
                            result_queue.put(("reasoning", reasoning))

                    elif kind == "on_tool_start":
                        tool_name = event.get("name", "unknown")
                        tool_input = event.get("data", {}).get("input", {})
                        phase_logger.log_phase(
                            Phase.TOOL_EXECUTION, f"Tool gestartet: {tool_name}"
                        )
                        result_queue.put(("tool_start", tool_name))
                        tool_calls.append(
                            {"name": tool_name, "input": tool_input, "output": None}
                        )

                    elif kind == "on_tool_end":
                        tool_name = event.get("name", "unknown")
                        tool_output = event.get("data", {}).get("output", "")
                        phase_logger.log_phase(
                            Phase.TOOL_EXECUTION, f"Tool beendet: {tool_name}"
                        )
                        result_queue.put(("tool_end", tool_name))
                        fresh = scope.sources[sources_sent:]
                        if fresh:
                            sources_sent += len(fresh)
                            result_queue.put(("sources", list(fresh)))
                        while scope.warnings:
                            result_queue.put(("warning", scope.warnings.pop(0)))
                        result_queue.put(
                            ("tool_result", (tool_name, str(tool_output)[:2000]))
                        )
                        if tool_calls:
                            for tc in tool_calls:
                                if tc["name"] == tool_name and tc["output"] is None:
                                    tc["output"] = str(tool_output)[:2000]
                                    break

                if cancel_event.is_set():
                    phase_logger.log_phase(
                        Phase.AGENT_RESPONSE, "Antwort vom Benutzer abgebrochen"
                    )
                else:
                    phase_logger.log_phase(
                        Phase.AGENT_RESPONSE,
                        f"Antwort gestreamt | Tokens: {len(full_response)}",
                    )
                    # Signal an Frontend: Thinking abgeschlossen (zum
                    # Zuklappen des offenen Blocks).
                    result_queue.put(("reasoning_done", None))
                    result_queue.put(("done", full_response))

            except Exception as e:
                import traceback

                traceback.print_exc()
                phase_logger.log_phase(
                    Phase.AGENT_RESPONSE, f"Fehler: {str(e)[:100]}", duration=0.0
                )
                result_queue.put(("error", str(e)))

        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_agent_async())
            finally:
                loop.close()

        thread = threading.Thread(target=run_in_thread)
        thread.start()

        try:
            while True:
                msg_type, msg_data = result_queue.get()

                if msg_type == "done":
                    # Antwort demaskieren bevor sie gespeichert wird
                    db = get_db_service()
                    demasked_response = msg_data
                    if demask_context["mapping"] and pii_filter:
                        try:
                            demasked_response = pii_filter.demask(
                                msg_data, demask_context["mapping"]
                            )
                            if demasked_response != msg_data:
                                logger.info(
                                    f"PII-Demaskierung: {len(demask_context['mapping'])} Platzhalter ersetzt"
                                )
                        except Exception as e:
                            logger.warning(f"PII-Demaskierung fehlgeschlagen: {e}")

                    db.save_message(final_session_id, "user", user_message)

                    # Reasoning als <think>-Tags vor die Antwort speichern,
                    # damit der Denk-Block beim Neuladen der History wieder
                    # als ausklappbarer Block erscheint.
                    saved_assistant = demasked_response
                    if full_reasoning:
                        reasoning_text = full_reasoning.strip()
                        if demask_context["mapping"] and pii_filter:
                            try:
                                reasoning_text = pii_filter.demask(
                                    reasoning_text, demask_context["mapping"]
                                )
                            except Exception as e:
                                logger.warning(
                                    f"PII-Demaskierung (Reasoning) fehlgeschlagen: {e}"
                                )
                        saved_assistant = (
                            f"<think>{reasoning_text}</think>\n" + demasked_response
                        )
                    if scope.sources:  # Quellen mit Score fuer die Anzeige im Verlauf
                        saved_assistant += (
                            "\n\n<sources>"
                            + json.dumps(scope.sources, ensure_ascii=False)
                            + "</sources>"
                        )
                    db.save_message(final_session_id, "assistant", saved_assistant)
                    yield f"data: {json.dumps({'done': True, 'session_id': final_session_id})}\n\n"
                    break

                elif msg_type == "cancelled":
                    break

                elif msg_type == "reasoning_done":
                    yield f"data: {json.dumps({'reasoning_done': True})}\n\n"

                elif msg_type == "reasoning":
                    yield f"data: {json.dumps({'reasoning': msg_data})}\n\n"

                elif msg_type == "token":
                    yield f"data: {json.dumps({'token': msg_data})}\n\n"

                elif msg_type == "tool_start":
                    yield f"data: {json.dumps({'tool_start': msg_data})}\n\n"

                elif msg_type == "tool_end":
                    yield f"data: {json.dumps({'tool_end': msg_data})}\n\n"

                elif msg_type == "warning":
                    yield f"data: {json.dumps({'warning': msg_data})}\n\n"

                elif msg_type == "sources":
                    yield f"data: {json.dumps({'source_list': msg_data})}\n\n"

                elif msg_type == "tool_result":
                    tool_name, tool_output = msg_data
                    payload = {
                        "tool_result": {"name": tool_name, "output": tool_output}
                    }
                    yield f"data: {json.dumps(payload)}\n\n"

                elif msg_type == "error":
                    yield f"data: {json.dumps({'error': msg_data})}\n\n"
                    break
        except GeneratorExit:
            _set_cancelled(final_session_id)
        finally:
            thread.join(timeout=1)
            _clear_cancelled(final_session_id)

    return Response(generate(), mimetype="text/event-stream")


@bp.route("/chat/stop", methods=["POST"])
@auth_required_api
def stop_chat():
    """Bricht den laufenden Chat-Stream für eine Session ab."""
    data = request.get_json() or {}
    session_id = data.get("session_id")
    # Nur eigene Chats abbrechen (die Session-ID allein ist kein Berechtigungsnachweis).
    if session_id and get_db_service().get_chat_session(
        session_id, user_id=current_user()["id"]
    ):
        _set_cancelled(session_id)
    return jsonify({"success": True})


@bp.route("/api/stt", methods=["POST"])
@auth_required_api
def stt():
    """Wandelt ein aufgenommenes Audio-Blob in Text um (OpenAI-kompatibles STT)."""
    if "audio" not in request.files:
        return jsonify({"error": "Keine Audiodatei"}), 400

    audio_file = request.files["audio"]
    if not audio_file or audio_file.filename == "":
        return jsonify({"error": "Leere Audiodatei"}), 400

    db = get_db_service()
    settings = SettingsService(db.get_session())

    base_url = settings.get("STT_BASEURL", "http://localhost:11434/v1")
    api_key = settings.get("STT_API_KEY", "ollama")
    model = settings.get("STT_MODEL", "whisper-1")

    try:
        audio_bytes = audio_file.read()
        file_obj = io.BytesIO(audio_bytes)
        file_obj.name = audio_file.filename or "recording.webm"

        client = openai.OpenAI(base_url=base_url, api_key=api_key)
        transcript = client.audio.transcriptions.create(model=model, file=file_obj)
        return jsonify({"text": transcript.text})
    except Exception as e:
        logger.exception("STT Transkription fehlgeschlagen")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# React-SPA Catch-all
# =============================================================================

# Alle nicht von Flask/API/Assets bedienten GET-Pfade sind clientseitige
# React-Router-Routen und liefern dieselbe index.html aus. Bewusst über einen
# 404-Handler (echter Catch-all) statt einer Routen-Whitelist: neue SPA-Seiten
# funktionieren damit automatisch, ohne hier etwas nachzutragen.
_RESERVED_PREFIXES = ("/api/", "/static/", "/user/", "/ws/")
_RESERVED_EXACT = {"/health", "/logout"}


@bp.app_errorhandler(404)
def spa_fallback(error):
    path = request.path

    # Backend-/API-/Asset-Pfade niemals mit der SPA überschreiben.
    if (
        request.method != "GET"
        or path.startswith(_RESERVED_PREFIXES)
        or path in _RESERVED_EXACT
    ):
        return error.get_response()

    # Nur Navigation (HTML) oder extension-lose Pfade als SPA ausliefern;
    # fehlende Dateien mit Endung bleiben echte 404s.
    accepts_html = "text/html" in request.headers.get("Accept", "")
    looks_like_file = "." in os.path.basename(path)
    if accepts_html or not looks_like_file:
        return serve_spa()

    return error.get_response()

