marked.setOptions({
    breaks: true,
    gfm: true,
    highlight: function(code, lang) {
        return code;
    }
});

const messagesContainer = document.getElementById('messagesContainer');
const chatForm = document.getElementById('chatForm');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebarOverlay = document.getElementById('sidebarOverlay');
const newChatBtn = document.getElementById('newChatBtn');
const sessionList = document.getElementById('sessionList');

userInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 200) + 'px';
});

userInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
    }
});

let currentSessionId = null;

sidebarToggle.addEventListener('click', () => {
    const isOpen = sidebar.classList.contains('translate-x-0');
    if (isOpen) {
        sidebar.classList.add('-translate-x-full');
        sidebar.classList.remove('translate-x-0');
        sidebarOverlay.classList.add('hidden');
    } else {
        sidebar.classList.remove('-translate-x-full');
        sidebar.classList.add('translate-x-0');
        sidebarOverlay.classList.remove('hidden');
    }
});

sidebarOverlay.addEventListener('click', () => {
    sidebar.classList.add('-translate-x-full');
    sidebar.classList.remove('translate-x-0');
    sidebarOverlay.classList.add('hidden');
});

async function loadSessions() {
    try {
        const response = await fetch('/api/sessions');
        const sessions = await response.json();
        renderSessionList(sessions);
        return sessions;
    } catch (error) {
        console.error('Error loading sessions:', error);
        return [];
    }
}

function renderSessionList(sessions) {
    if (sessions.length === 0) {
        sessionList.innerHTML = '<div class="text-center text-white/50 py-8 text-sm">Keine Chats vorhanden</div>';
        return;
    }

    sessionList.innerHTML = sessions.map(sess => `
        <div class="session-item ${sess.id === currentSessionId ? 'bg-white/25' : ''} px-4 py-2 rounded-lg cursor-pointer flex justify-between items-center hover:bg-white/10 transition-colors" data-id="${sess.id}">
            <span class="text-sm truncate">${escapeHtml(sess.title || 'Neuer Chat')}</span>
            <button class="session-delete bg-transparent border-0 text-white/60 cursor-pointer p-1 rounded opacity-0 hover:opacity-100 hover:text-red-300 transition-all" onclick="deleteSession('${sess.id}', event)">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        </div>
    `).join('');

    document.querySelectorAll('.session-item').forEach(item => {
        item.addEventListener('click', (e) => {
            if (!e.target.closest('.session-delete')) {
                switchSession(item.dataset.id);
            }
        });
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function createNewSession() {
    try {
        const response = await fetch('/api/sessions', { method: 'POST' });
        const session = await response.json();
        currentSessionId = session.id;
        messagesContainer.innerHTML = '';
        await loadSessions();
        closeSidebarMobile();
    } catch (error) {
        console.error('Error creating session:', error);
    }
}

async function switchSession(sessionId) {
    currentSessionId = sessionId;
    try {
        const response = await fetch(`/api/sessions/${sessionId}`);
        const session = await response.json();
        messagesContainer.innerHTML = '';
        renderMessages(session.messages || []);
        highlightActiveSession();
        closeSidebarMobile();
    } catch (error) {
        console.error('Error switching session:', error);
    }
}

function renderMessages(messages) {
    messages.forEach(msg => {
        if (msg.role === 'user') {
            addMessage('user', msg.content, false);
        } else {
            addMessage('assistant', msg.content, true);
        }
    });
}

function highlightActiveSession() {
    document.querySelectorAll('.session-item').forEach(item => {
        item.classList.toggle('bg-white/25', item.dataset.id === currentSessionId);
    });
}

async function deleteSession(sessionId, event) {
    event.stopPropagation();
    if (!confirm('Chat wirklich löschen?')) return;

    try {
        await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
        if (currentSessionId === sessionId) {
            currentSessionId = null;
            messagesContainer.innerHTML = '';
        }
        const sessions = await loadSessions();
        if (sessions.length > 0 && !currentSessionId) {
            switchSession(sessions[0].id);
        }
    } catch (error) {
        console.error('Error deleting session:', error);
    }
}

function closeSidebarMobile() {
    if (window.innerWidth <= 1024) {
        sidebar.classList.add('-translate-x-full');
        sidebar.classList.remove('translate-x-0');
        sidebarOverlay.classList.add('hidden');
    }
}

newChatBtn.addEventListener('click', createNewSession);

function addMessage(role, content, isMarkdown = false) {
    const div = document.createElement('div');
    div.className = `message ${role}`;

    if (isMarkdown && role === 'assistant') {
        div.innerHTML = DOMPurify.sanitize(marked.parse(content));
    } else {
        div.textContent = content;
    }

    messagesContainer.appendChild(div);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    return div;
}

function addLoadingMessage() {
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
    messagesContainer.appendChild(div);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    return div;
}

function updateMarkdown(div, content) {
    let processed = content
        .replace(/<tool_call>([\s\S]*?)<\/think>/g, function(match, thinking) {
            return '<details class="thinking-block"><summary>Denken</summary><pre>' + thinking.trim() + '</pre></details>';
        })
        .replace(/<tool_call>([\s\S]*)$/g, function(match, thinking) {
            return '<details class="thinking-block" open><summary>Denken (läuft...)</summary><pre>' + thinking.trim() + '</pre></details>';
        });
    div.innerHTML = DOMPurify.sanitize(marked.parse(processed));
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function updateThinkingBlock(div, reasoning) {
    let thinkingDiv = div.querySelector('.thinking-block');
    if (!thinkingDiv) {
        thinkingDiv = document.createElement('details');
        thinkingDiv.className = 'thinking-block';
        thinkingDiv.open = false;
        thinkingDiv.innerHTML = '<summary>Denken</summary><pre></pre>';
        div.insertBefore(thinkingDiv, div.firstChild);
    }
    thinkingDiv.querySelector('pre').textContent = reasoning;
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function addToolIndicator(messageDiv, toolName) {
    const indicator = document.createElement('div');
    indicator.className = 'tool-indicator';
    indicator.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-4 h-4 inline">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
        </svg>
        ${toolName}
    `;
    messageDiv.appendChild(indicator);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

async function sendMessage(message) {
    const userMsgDiv = addMessage('user', message);
    const assistantMsgDiv = addLoadingMessage();

    userInput.disabled = true;
    sendBtn.disabled = true;

    let fullResponse = '';
    let isFirstToken = true;

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message, session_id: currentSessionId })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    if (data.trim()) {
                        try {
                            const parsed = JSON.parse(data);

                            if (parsed.token) {
                                if (isFirstToken) {
                                    assistantMsgDiv.innerHTML = '';
                                    isFirstToken = false;
                                }
                                fullResponse += parsed.token;
                                updateMarkdown(assistantMsgDiv, fullResponse);
                            }

                            if (parsed.reasoning) {
                                if (isFirstToken) {
                                    assistantMsgDiv.innerHTML = '';
                                    isFirstToken = false;
                                }
                                if (!window.reasoningContent) window.reasoningContent = '';
                                window.reasoningContent += parsed.reasoning;
                                updateThinkingBlock(assistantMsgDiv, window.reasoningContent);
                            }

                            if (parsed.tool_start) {
                                addToolIndicator(assistantMsgDiv, parsed.tool_start);
                            }

                            if (parsed.tool_result) {
                                const toolResult = parsed.tool_result;
                                const details = document.createElement('details');
                                details.className = 'my-2 text-sm';
                                const summary = document.createElement('summary');
                                summary.textContent = `[Tool: ${toolResult.name}]`;
                                summary.className = 'cursor-pointer text-slate-700 dark:text-slate-400 font-medium';
                                const pre = document.createElement('pre');
                                pre.className = 'bg-gray-100 dark:bg-gray-700 p-2 rounded mt-1 overflow-x-auto';
                                pre.textContent = toolResult.output;
                                details.appendChild(summary);
                                details.appendChild(pre);
                                assistantMsgDiv.appendChild(details);
                                messagesContainer.scrollTop = messagesContainer.scrollHeight;
                            }

                            if (parsed.sources) {
                                fullResponse += parsed.sources;
                                updateMarkdown(assistantMsgDiv, fullResponse);
                            }

                            if (parsed.done) {
                                if (parsed.session_id && !currentSessionId) {
                                    currentSessionId = parsed.session_id;
                                    loadSessions();
                                }
                            }

                            if (parsed.error) {
                                assistantMsgDiv.innerHTML = `<div class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-red-700 dark:text-red-200">Fehler: ${parsed.error}</div>`;
                            }
                        } catch (e) {
                            // Ignore parse errors
                        }
                    }
                }
            }
        }
    } catch (error) {
        assistantMsgDiv.innerHTML = `<div class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-red-700 dark:text-red-200">Fehler: ${error.message}</div>`;
    }

    if (!fullResponse && isFirstToken) {
        assistantMsgDiv.innerHTML = '<div class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-red-700 dark:text-red-200">Keine Antwort erhalten. Bitte versuche es erneut.</div>';
    }

    userInput.disabled = false;
    sendBtn.disabled = false;
    userInput.focus();
}

chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const message = userInput.value.trim();
    if (message) {
        userInput.value = '';
        userInput.style.height = 'auto';
        sendMessage(message);
    }
});

(async function init() {
    const sessions = await loadSessions();
    if (sessions.length > 0) {
        switchSession(sessions[0].id);
    }
    userInput.focus();
})();