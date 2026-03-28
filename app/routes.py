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
    
    input_data = {"messages": messages}
    
    def generate():
        result_queue = queue.Queue()
        full_response = ""
        
        async def run_agent_async():
            nonlocal full_response
            try:
                phase_logger.log_phase(Phase.AGENT_START, "Agent-Stream gestartet")
                
                async for event in agent.astream_events(input_data, version="v1"):
                    kind = event.get("event")
                    phase_logger.log_phase(Phase.TOOL_EXECUTION, f"Event: {kind} | Data: {str(event.get('data', {}))[:200]}")
                    
                    if kind == "on_chat_model_stream":
                        content = event["data"]["chunk"].content
                        if content:
                            full_response += content
                            result_queue.put(('token', content))
                    
                    elif kind == "on_chain_stream":
                        chunk = event.get("data", {}).get("chunk", {})
                        messages = chunk.get("model", {}).get("messages", []) if isinstance(chunk, dict) else []
                        for msg in messages:
                            if hasattr(msg, "content") and msg.content:
                                if not full_response:
                                    full_response = msg.content
                                    result_queue.put(('token', msg.content))
                    
                    elif kind == "on_chain_end":
                        output = event.get("data", {}).get("output", {})
                        messages = []
                        if isinstance(output, dict):
                            messages = output.get("model", {}).get("messages", [])
                        for msg in messages:
                            if hasattr(msg, "content") and msg.content:
                                if not full_response:
                                    full_response = msg.content
                                    result_queue.put(('token', msg.content))
                    
                    elif kind == "on_tool_start":
                        tool_name = event.get("name", "unknown")
                        phase_logger.log_phase(Phase.TOOL_EXECUTION, f"Tool gestartet: {tool_name}")
                        result_queue.put(('tool_start', tool_name))
                    
                    elif kind == "on_tool_end":
                        tool_name = event.get("name", "unknown")
                        phase_logger.log_phase(Phase.TOOL_EXECUTION, f"Tool beendet: {tool_name}")
                        result_queue.put(('tool_end', tool_name))
                
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
                    SESSION_HISTORY[user].append({'role': 'assistant', 'content': msg_data})
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    break
                
                elif msg_type == 'token':
                    yield f"data: {json.dumps({'token': msg_data})}\n\n"
                
                elif msg_type == 'tool_start':
                    yield f"data: {json.dumps({'tool_start': msg_data})}\n\n"
                
                elif msg_type == 'tool_end':
                    yield f"data: {json.dumps({'tool_end': msg_data})}\n\n"
                
                elif msg_type == 'error':
                    yield f"data: {json.dumps({'error': msg_data})}\n\n"
                    break
        except GeneratorExit:
            pass
        finally:
            thread.join(timeout=1)
    
    return Response(generate(), mimetype='text/event-stream')