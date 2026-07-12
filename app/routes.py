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

import json
import io
import asyncio
import queue
import threading
import logging
from flask import Blueprint, render_template, request, session, redirect, url_for, flash, Response, current_app, jsonify
from werkzeug.security import check_password_hash
import openai

from app.auth import auth_required
from app.database_service import get_db_service
from app.settings_service import SettingsService
from app.utils.phase_logger import phase_logger, Phase
from app import wait_for_resources, resources_ready

bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__)

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

@bp.route('/api/sessions', methods=['GET'])
@auth_required
def get_sessions():
    """List all sessions"""
    db = get_db_service()
    sessions = db.list_sessions()

    result = []
    for sess in sessions:
        result.append({
            'id': sess.id,
            'title': sess.title,
            'created_at': sess.created_at.isoformat() if sess.created_at else None,
            'updated_at': sess.updated_at.isoformat() if sess.updated_at else None
        })

    return jsonify(result)


@bp.route('/api/sessions', methods=['POST'])
@auth_required
def new_session():
    """Create a new session"""
    db = get_db_service()
    new_sess = db.create_session()

    return jsonify({
        'id': new_sess.id,
        'title': new_sess.title,
        'created_at': new_sess.created_at.isoformat() if new_sess.created_at else None,
        'updated_at': new_sess.updated_at.isoformat() if new_sess.updated_at else None
    })


@bp.route('/api/sessions/<session_id>', methods=['GET'])
@auth_required
def get_session_messages(session_id):
    """Get session with messages"""
    db = get_db_service()
    sess = db.get_chat_session(session_id)

    if not sess:
        return jsonify({'error': 'Session nicht gefunden'}), 404

    messages = db.get_messages(session_id)

    message_dicts = []
    for msg in messages:
        message_dicts.append({
            'role': msg.role,
            'content': msg.content,
            'created_at': msg.created_at.isoformat() if msg.created_at else None
        })

    return jsonify({
        'id': sess.id,
        'title': sess.title,
        'created_at': sess.created_at.isoformat() if sess.created_at else None,
        'updated_at': sess.updated_at.isoformat() if sess.updated_at else None,
        'messages': message_dicts
    })


@bp.route('/api/sessions/<session_id>', methods=['DELETE'])
@auth_required
def delete_session_route(session_id):
    """Delete a session"""
    db = get_db_service()
    deleted = db.delete_session(session_id)

    if not deleted:
        return jsonify({'error': 'Session nicht gefunden'}), 404

    return jsonify({'success': True})


@bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Docker (Liveness). ready=False waehrend
    die Embedding-Modelle im Hintergrund geladen werden."""
    return {'status': 'healthy', 'ready': resources_ready()}, 200


@bp.route('/api/ingestion-status', methods=['GET'])
@auth_required
def ingestion_status():
    """Geteilter Ingestion-Status fuer den Navbar-Indikator per Polling."""
    return jsonify(current_app.extensions['ingestion_status'])


@bp.route('/', methods=['GET'])
@auth_required
def index():
    return render_template('index.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')

        db = get_db_service()
        settings = SettingsService(db.get_session())
        password_hash = settings.get('APP_PASSWORD_HASH')

        if password_hash and check_password_hash(password_hash, password):
            session['authenticated'] = True
            return redirect(url_for('main.index'))

        flash('Ungültiges Passwort')

    return render_template('login.html')


@bp.route('/logout', methods=['GET'])
def logout():
    session.clear()
    return redirect(url_for('main.login'))


@bp.route('/history/<session_id>', methods=['GET'])
@auth_required
def history(session_id):
    db = get_db_service()
    sess = db.get_chat_session(session_id)

    if not sess:
        return {'error': 'Session nicht gefunden'}, 404

    messages = db.get_messages(session_id)

    message_dicts = []
    for msg in messages:
        message_dicts.append({
            'role': msg.role,
            'content': msg.content,
            'created_at': msg.created_at.isoformat() if msg.created_at else None
        })

    return {'history': message_dicts}


@bp.route('/chat', methods=['POST'])
@auth_required
def chat():
    data = request.get_json()
    user_message = data.get('message', '')
    session_id = data.get('session_id')

    if not user_message:
        return Response('data: {"error": "Keine Nachricht"}\n\n',
                       mimetype='text/event-stream')

    db = get_db_service()
    final_session_id = session_id
    sess = None

    if session_id:
        sess = db.get_chat_session(session_id)
        if not sess:
            return Response('data: {"error": "Ungültige Session"}\n\n',
                           mimetype='text/event-stream')
    else:
        new_sess = db.create_session()
        final_session_id = new_sess.id
        sess = new_sess

    if not sess.title:
        title = user_message[:50] + ('...' if len(user_message) > 50 else '')
        db.update_session_title(final_session_id, title)

    phase_logger.log_phase(Phase.USER_INPUT, f"User-Query: {user_message[:100]}...")

    agent = current_app.extensions.get("agent")
    if not agent:
        try:
            ready = wait_for_resources(timeout=180)
        except RuntimeError as e:
            return Response(f'data: {{"error": "{e}"}}\n\n',
                           mimetype='text/event-stream')
        if not ready:
            return Response('data: {"error": "RAG-System wird noch initialisiert '
                            '(Embedding-Modell lädt). Bitte in wenigen Sekunden '
                            'erneut versuchen."}\n\n',
                           mimetype='text/event-stream')
        agent = current_app.extensions.get("agent")

    if not agent:
        return Response('data: {"error": "Agent nicht initialisiert"}\n\n',
                       mimetype='text/event-stream')

    messages = db.get_messages(final_session_id, limit=10)
    message_list = []

    for msg in messages[-10:]:
        role = "user" if msg.role == 'user' else "assistant"
        message_list.append({"role": role, "content": msg.content})

    message_list.append({"role": "user", "content": user_message})

    from logging import getLogger
    logger = getLogger(__name__)
    logger.info(f"[DEBUG] Messages an Agent: {len(message_list)} Nachrichten")

    input_data = {"messages": message_list}

    def generate():
        result_queue = queue.Queue()
        full_response = ""
        tool_calls = []
        cancel_event = _get_cancel_event(final_session_id)
        cancel_event.clear()

        async def run_agent_async():
            nonlocal full_response
            try:
                phase_logger.log_phase(Phase.AGENT_START, "Agent-Stream gestartet")

                async for event in agent.astream_events(input_data, version="v2"):
                    if cancel_event.is_set():
                        result_queue.put(('cancelled', None))
                        break

                    kind = event.get("event")

                    if kind == "on_chat_model_stream":
                        chunk = event["data"]["chunk"]
                        content = chunk.content

                        reasoning = None
                        if hasattr(chunk, 'additional_kwargs') and chunk.additional_kwargs:
                            reasoning = chunk.additional_kwargs.get("reasoning_content")

                        if content:
                            full_response += content
                            result_queue.put(('token', content))

                        if reasoning:
                            result_queue.put(('reasoning', reasoning))

                    elif kind == "on_tool_start":
                        tool_name = event.get("name", "unknown")
                        tool_input = event.get("data", {}).get("input", {})
                        phase_logger.log_phase(Phase.TOOL_EXECUTION, f"Tool gestartet: {tool_name}")
                        result_queue.put(('tool_start', tool_name))
                        tool_calls.append({
                            "name": tool_name,
                            "input": tool_input,
                            "output": None
                        })

                    elif kind == "on_tool_end":
                        tool_name = event.get("name", "unknown")
                        tool_output = event.get("data", {}).get("output", "")
                        phase_logger.log_phase(Phase.TOOL_EXECUTION, f"Tool beendet: {tool_name}")
                        result_queue.put(('tool_end', tool_name))
                        result_queue.put(('tool_result', (tool_name, str(tool_output)[:2000])))
                        if tool_calls:
                            for tc in tool_calls:
                                if tc["name"] == tool_name and tc["output"] is None:
                                    tc["output"] = str(tool_output)[:2000]
                                    break

                if cancel_event.is_set():
                    phase_logger.log_phase(Phase.AGENT_RESPONSE, "Antwort vom Benutzer abgebrochen")
                else:
                    phase_logger.log_phase(Phase.AGENT_RESPONSE, f"Antwort gestreamt | Tokens: {len(full_response)}")
                    result_queue.put(('done', full_response))

            except Exception as e:
                import traceback
                traceback.print_exc()
                phase_logger.log_phase(Phase.AGENT_RESPONSE, f"Fehler: {str(e)[:100]}", duration=0.0)
                result_queue.put(('error', str(e)))

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

                if msg_type == 'done':
                    db = get_db_service()
                    db.save_message(final_session_id, 'user', user_message)
                    db.save_message(final_session_id, 'assistant', msg_data)
                    yield f"data: {json.dumps({'done': True, 'session_id': final_session_id})}\n\n"
                    break

                elif msg_type == 'cancelled':
                    break

                elif msg_type == 'reasoning':
                    yield f"data: {json.dumps({'reasoning': msg_data})}\n\n"

                elif msg_type == 'token':
                    yield f"data: {json.dumps({'token': msg_data})}\n\n"

                elif msg_type == 'tool_start':
                    yield f"data: {json.dumps({'tool_start': msg_data})}\n\n"

                elif msg_type == 'tool_end':
                    yield f"data: {json.dumps({'tool_end': msg_data})}\n\n"

                elif msg_type == 'tool_result':
                    tool_name, tool_output = msg_data
                    payload = {'tool_result': {'name': tool_name, 'output': tool_output}}
                    yield f"data: {json.dumps(payload)}\n\n"

                elif msg_type == 'error':
                    yield f"data: {json.dumps({'error': msg_data})}\n\n"
                    break
        except GeneratorExit:
            _set_cancelled(final_session_id)
        finally:
            thread.join(timeout=1)
            _clear_cancelled(final_session_id)

    return Response(generate(), mimetype='text/event-stream')


@bp.route('/chat/stop', methods=['POST'])
@auth_required
def stop_chat():
    """Bricht den laufenden Chat-Stream für eine Session ab."""
    data = request.get_json() or {}
    session_id = data.get('session_id')
    if session_id:
        _set_cancelled(session_id)
    return jsonify({'success': True})


@bp.route('/api/stt', methods=['POST'])
@auth_required
def stt():
    """Wandelt ein aufgenommenes Audio-Blob in Text um (OpenAI-kompatibles STT)."""
    if 'audio' not in request.files:
        return jsonify({'error': 'Keine Audiodatei'}), 400

    audio_file = request.files['audio']
    if not audio_file or audio_file.filename == '':
        return jsonify({'error': 'Leere Audiodatei'}), 400

    db = get_db_service()
    settings = SettingsService(db.get_session())

    base_url = settings.get('STT_BASEURL', 'http://localhost:11434/v1')
    api_key = settings.get('STT_API_KEY', 'ollama')
    model = settings.get('STT_MODEL', 'whisper-1')

    try:
        audio_bytes = audio_file.read()
        file_obj = io.BytesIO(audio_bytes)
        file_obj.name = audio_file.filename or 'recording.webm'

        client = openai.OpenAI(base_url=base_url, api_key=api_key)
        transcript = client.audio.transcriptions.create(model=model, file=file_obj)
        return jsonify({'text': transcript.text})
    except Exception as e:
        logger.exception("STT Transkription fehlgeschlagen")
        return jsonify({'error': str(e)}), 500
