import json
import asyncio
import queue
import threading
from flask import Blueprint, render_template, request, session, redirect, url_for, flash, Response, current_app
from app import USERS
from src.utils.phase_logger import phase_logger, Phase

bp = Blueprint('main', __name__)

SESSION_HISTORY = {}


def get_session_id():
    return session.get('user', 'anonymous')


@bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Docker"""
    return {'status': 'healthy'}, 200


@bp.route('/', methods=['GET'])
def index():
    if 'user' not in session:
        return redirect(url_for('main.login'))
    # Reset history on page load/refresh for fresh start
    SESSION_HISTORY[session['user']] = []
    return render_template('index.html', username=session['user'])


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in USERS and USERS[username] == password:
            session['user'] = username
            SESSION_HISTORY[username] = []
            return redirect(url_for('main.index'))
        flash('Ungültige Benutzername oder Passwort')
    
    return render_template('login.html')


@bp.route('/logout', methods=['GET'])
def logout():
    user = session.get('user')
    if user and user in SESSION_HISTORY:
        del SESSION_HISTORY[user]
    session.clear()
    return redirect(url_for('main.login'))


@bp.route('/history', methods=['GET'])
def history():
    if 'user' not in session:
        return {'error': 'Nicht authentifiziert'}, 401
    user = get_session_id()
    return {'history': SESSION_HISTORY.get(user, [])}


@bp.route('/chat', methods=['POST'])
def chat():
    if 'user' not in session:
        return Response('data: {"error": "Nicht authentifiziert"}\n\n', 
                       mimetype='text/event-stream')
    
    data = request.get_json()
    user_message = data.get('message', '')
    
    if not user_message:
        return Response('data: {"error": "Keine Nachricht"}\n\n',
                       mimetype='text/event-stream')
    
    phase_logger.log_phase(Phase.USER_INPUT, f"User-Query: {user_message[:100]}...")
    
    agent = current_app.extensions.get("agent")
    
    if not agent:
        return Response('data: {"error": "Agent nicht initialisiert"}\n\n',
                       mimetype='text/event-stream')
    
    user = get_session_id()
    history = SESSION_HISTORY.get(user, [])
    messages = []
    
    for msg in history[-10:]:
        role = "user" if msg['role'] == 'user' else "assistant"
        messages.append({"role": role, "content": msg['content']})
    
    messages.append({"role": "user", "content": user_message})

    # Debug-Logging: Was wird an den Agent übergeben?
    from logging import getLogger
    logger = getLogger(__name__)
    logger.info(f"[DEBUG] Messages an Agent: {len(messages)} Nachrichten")
    for i, msg in enumerate(messages):
        content_preview = msg.get('content', '')[:200]
        logger.info(f"[DEBUG] Message {i}: role={msg.get('role')}, content={content_preview}...")

    input_data = {"messages": messages}
    
    def generate():
        result_queue = queue.Queue()
        full_response = ""
        tool_calls = []  # Speichert Tool-Aufrufe und Ergebnisse

        async def run_agent_async():
            nonlocal full_response
            try:
                phase_logger.log_phase(Phase.AGENT_START, "Agent-Stream gestartet")

                async for event in agent.astream_events(input_data, version="v2"):
                    kind = event.get("event")

                    if kind == "on_chat_model_stream":
                        content = event["data"]["chunk"].content
                        if content:
                            full_response += content
                            result_queue.put(('token', content))

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
                        # Stream das Tool-Output sofort
                        result_queue.put(('tool_result', (tool_name, str(tool_output)[:2000])))
                        # Speichere das Tool-Ergebnis
                        if tool_calls:
                            for tc in tool_calls:
                                if tc["name"] == tool_name and tc["output"] is None:
                                    tc["output"] = str(tool_output)[:2000]  # Limit für Memory
                                    break

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
                    SESSION_HISTORY[user] = SESSION_HISTORY.get(user, [])
                    SESSION_HISTORY[user].append({'role': 'user', 'content': user_message})
                    # Speichere nur die finale Antwort ohne Tool-Outputs (die wurden live gestreamt)
                    SESSION_HISTORY[user].append({'role': 'assistant', 'content': msg_data})
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    break
                
                elif msg_type == 'token':
                    yield f"data: {json.dumps({'token': msg_data})}\n\n"
                
                elif msg_type == 'tool_start':
                    yield f"data: {json.dumps({'tool_start': msg_data})}\n\n"
                
                elif msg_type == 'tool_end':
                    yield f"data: {json.dumps({'tool_end': msg_data})}\n\n"

                elif msg_type == 'tool_result':
                    tool_name, tool_output = msg_data
                    yield f"data: {json.dumps({'tool_result': {'name': tool_name, 'output': tool_output}})}\n\n"

                elif msg_type == 'error':
                    yield f"data: {json.dumps({'error': msg_data})}\n\n"
                    break
        except GeneratorExit:
            pass
        finally:
            thread.join(timeout=1)
    
    return Response(generate(), mimetype='text/event-stream')