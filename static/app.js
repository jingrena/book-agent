// 全局状态
let isProcessing = false;
let streamingBubble = null;
let abortController = null;
let browserSessionId = localStorage.getItem('browser_session_id') || '';
if (!browserSessionId) {
    browserSessionId = 'sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    localStorage.setItem('browser_session_id', browserSessionId);
}

// DOM 元素
const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
const stopBtn = document.getElementById('stopBtn');
const statusEl = document.getElementById('status');
const processLog = document.getElementById('processLog');
const traceReport = document.getElementById('traceReport');
const memoryList = document.getElementById('memoryList');
const bookList = document.getElementById('bookList');
const skillList = document.getElementById('skillList');
const sessionListEl = document.getElementById('sessionList');

// 初始化
inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

inputEl.addEventListener('input', () => {
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
});

loadSessionList();
loadChatHistory();
loadMemory();
loadBooks();
loadSkills();

// 发送消息
async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text || isProcessing) return;

    isProcessing = true;
    sendBtn.disabled = true;
    stopBtn.style.display = 'inline-block';
    statusEl.textContent = '思考中...';
    statusEl.className = 'status thinking';
    inputEl.value = '';
    inputEl.style.height = 'auto';

    addMessage('user', text);
    processLog.innerHTML = '';

    abortController = new AbortController();

    try {
        const response = await fetch('/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, session_id: browserSessionId }),
            signal: abortController.signal,
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let currentEvent = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    currentEvent = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    const dataStr = line.slice(6);
                    try {
                        const data = JSON.parse(dataStr);
                        handleSSEEvent(currentEvent, data);
                    } catch (e) {}
                }
            }
        }
    } catch (err) {
        if (err.name === 'AbortError') {
            addMessage('system', '已停止生成');
        } else {
            addMessage('system', '连接出错：' + err.message);
        }
    }

    isProcessing = false;
    sendBtn.disabled = false;
    stopBtn.style.display = 'none';
    abortController = null;
    statusEl.textContent = '就绪';
    statusEl.className = 'status';
    inputEl.focus();
}

// 停止生成
function stopGeneration() {
    if (abortController) {
        abortController.abort();
    }
    if (streamingBubble) {
        streamingBubble.parentElement.classList.remove('streaming');
        streamingBubble.classList.remove('streaming-cursor');
        streamingBubble = null;
    }
}

// 处理 SSE 事件
function handleSSEEvent(eventType, data) {
    switch (eventType) {
        case 'reply_start':
            // 创建流式气泡
            streamingBubble = createStreamingBubble();
            break;

        case 'token':
            // 第一次收到 token 时自动创建流式气泡
            if (!streamingBubble) {
                streamingBubble = createStreamingBubble();
            }
            if (data.text) {
                streamingBubble.textContent += data.text;
                messagesEl.scrollTop = messagesEl.scrollHeight;
            }
            break;

        case 'done':
            // 流式结束，固化气泡，显示追踪报告
            if (streamingBubble) {
                streamingBubble.parentElement.classList.remove('streaming');
                streamingBubble.classList.remove('streaming-cursor');
            }
            streamingBubble = null;
            renderTraceReport(data.trace);
            loadMemory();
            loadBooks();
            loadSkills();
            loadSessionList();
            break;

        case 'route':
        case 'step':
        case 'tool':
        case 'thinking':
        case 'specialist':
        case 'workflow_start':
        case 'workflow_end':
        case 'memory':
            addProcessItem(data.message || '', eventType);
            break;

        case 'blocked':
            addMessage('system', '输入被拦截：' + data.reason);
            break;

        case 'confirm_request':
            showConfirmDialog(data.confirm_id, data.detail, data.fields);
            break;

        case 'error':
            addMessage('system', '出错了：' + data.message);
            break;

        case 'heartbeat':
            break;
    }
}

// 创建流式消息气泡
function createStreamingBubble() {
    const div = document.createElement('div');
    div.className = 'msg assistant streaming';
    const bubble = document.createElement('div');
    bubble.className = 'bubble streaming-cursor';
    div.appendChild(bubble);
    messagesEl.appendChild(div);
    return bubble;
}

// 添加消息气泡
function addMessage(role, content) {
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    div.innerHTML = `<div class="bubble">${escapeHtml(content)}</div>`;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

// 添加过程日志
function addProcessItem(text, type) {
    if (type === 'route') type = 'route';
    else if (type === 'tool') type = 'tool';
    else if (type === 'thinking') type = 'thinking';
    else if (type === 'specialist') type = 'specialist';
    else if (type.startsWith('workflow')) type = 'workflow';
    else if (type === 'memory') type = 'memory';
    else type = 'step';

    const item = document.createElement('div');
    item.className = `process-item ${type}`;
    item.textContent = text.replace(/\s+/g, ' ').trim();
    processLog.appendChild(item);
    processLog.scrollTop = processLog.scrollHeight;
    switchTab('process');
}

// 渲染追踪报告
function renderTraceReport(trace) {
    if (!trace || !trace.total_ms) {
        traceReport.innerHTML = '<div class="process-empty">无追踪数据</div>';
        return;
    }

    let html = `
        <div class="trace-header">
            <span>总耗时：${trace.total_ms}ms</span>
            <span>总 Token：${trace.total_tokens}</span>
        </div>
    `;

    for (const span of trace.spans || []) {
        const tokenInfo = (span.token_in || span.token_out)
            ? `<span class="trace-span-token">${span.token_in}+${span.token_out}</span>`
            : '';
        html += `
            <div class="trace-span">
                <span class="trace-span-name">${escapeHtml(span.name)}</span>
                <span class="trace-span-time">${span.duration_ms}ms ${tokenInfo}</span>
            </div>
        `;
    }

    traceReport.innerHTML = html;
    switchTab('trace');
}

// 切换面板 Tab
function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelector(`.tab[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(`tab-${tabName}`).classList.add('active');
}

// 加载记忆
async function loadMemory() {
    try {
        const resp = await fetch('/memory');
        const data = await resp.json();
        if (data.memories && data.memories.length > 0) {
            memoryList.innerHTML = data.memories.map(m =>
                `<div class="memory-item">${escapeHtml(m)}</div>`
            ).join('');
        } else {
            memoryList.innerHTML = '<div class="process-empty">暂无记忆</div>';
        }
    } catch (e) {
        memoryList.innerHTML = '<div class="process-empty">加载失败</div>';
    }
}

// 清除记忆
async function clearMemory() {
    if (!confirm('确定要清除所有记忆吗？')) return;
    await fetch('/memory', { method: 'DELETE' });
    loadMemory();
}

// 加载书库
async function loadBooks() {
    try {
        const resp = await fetch('/books');
        const data = await resp.json();
        if (data.books && data.books.length > 0) {
            bookList.innerHTML = data.books.map(b => `
                <div class="book-item">
                    <div class="book-title">${escapeHtml(b.title)}</div>
                    <div class="book-meta">${escapeHtml(b.author)} · ${b.publish_date}</div>
                    <span class="book-category">${escapeHtml(b.category)}</span>
                </div>
            `).join('');
        } else {
            bookList.innerHTML = '<div class="process-empty">书库为空</div>';
        }
    } catch (e) {
        bookList.innerHTML = '<div class="process-empty">加载失败</div>';
    }
}

// HTML 转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 加载技能
async function loadSkills() {
    try {
        const resp = await fetch('/skills');
        const data = await resp.json();

        // 已安装的 Skill
        if (data.installed && data.installed.length > 0) {
            skillList.innerHTML = data.installed.map(s => `
                <div class="skill-item">
                    <div class="skill-header">
                        <span class="skill-name">${escapeHtml(s.name)}</span>
                    </div>
                    <div class="skill-meta">
                        ${s.tools && s.tools.length ? `<span class="skill-tools">工具：${s.tools.map(t => escapeHtml(typeof t === 'string' ? t : t)).join(', ')}</span>` : ''}
                    </div>
                </div>
            `).join('');
        } else {
            skillList.innerHTML = '<div class="process-empty">暂无已安装 Skill</div>';
        }

        // 可安装的 Skill
        const availableEl = document.getElementById('availableSkills');
        if (data.available && data.available.length > 0) {
            availableEl.innerHTML = '<div class="skill-section-title">可安装</div>' +
                data.available.map(s => `
                    <div class="skill-item available">
                        <div class="skill-header">
                            <span class="skill-name">${escapeHtml(s.name)}</span>
                        </div>
                        <div class="skill-desc">${escapeHtml(s.description)}</div>
                        <button class="btn-install" onclick="installSkill('${s.file_name}')">安装</button>
                    </div>
                `).join('');
        } else {
            availableEl.innerHTML = '';
        }
    } catch (e) {
        skillList.innerHTML = '<div class="process-empty">加载失败</div>';
    }
}

// 安装 Skill
async function installSkill(skillName) {
    try {
        const resp = await fetch(`/skills/${skillName}/install`, { method: 'POST' });
        const data = await resp.json();
        alert(data.message);
        loadSkills();
    } catch (e) {
        alert('安装失败：' + e.message);
    }
}

// 卸载 Skill
async function uninstallSkill(skillId) {
    if (!confirm(`确定要卸载 Skill "${skillId}" 吗？`)) return;
    try {
        const resp = await fetch(`/skills/${skillId}`, { method: 'DELETE' });
        const data = await resp.json();
        alert(data.message);
        loadSkills();
    } catch (e) {
        alert('卸载失败：' + e.message);
    }
}

// 重新加载 Skill
async function reloadSkills() {
    try {
        const resp = await fetch('/skills/reload', { method: 'POST' });
        const data = await resp.json();
        alert(`已重新加载 ${data.loaded.length} 个 Skill`);
        loadSkills();
    } catch (e) {
        alert('重新加载失败：' + e.message);
    }
}

// 加载对话历史
async function loadChatHistory() {
    try {
        const resp = await fetch(`/history/${browserSessionId}`);
        const data = await resp.json();
        if (data.messages && data.messages.length > 0) {
            messagesEl.innerHTML = '';
            for (const msg of data.messages) {
                if (msg.role === 'user' || msg.role === 'assistant') {
                    addMessage(msg.role, msg.content);
                }
            }
        } else {
            // 空会话显示欢迎
            messagesEl.innerHTML = `
                <div class="msg system">
                    <div class="bubble">你好！我是智能图书助手，可以帮你找书、推荐书、上架新书。试试说"推荐一本科幻小说"或"上架一本书"。</div>
                </div>`;
        }
    } catch (e) {
        messagesEl.innerHTML = `
            <div class="msg system">
                <div class="bubble">你好！我是智能图书助手，可以帮你找书、推荐书、上架新书。试试说"推荐一本科幻小说"或"上架一本书"。</div>
            </div>`;
    }
}

// 加载会话列表
async function loadSessionList() {
    try {
        const resp = await fetch('/history');
        const data = await resp.json();
        if (data.sessions && data.sessions.length > 0) {
            sessionListEl.innerHTML = data.sessions.map(s => `
                <div class="session-item ${s.id === browserSessionId ? 'active' : ''}"
                     onclick="switchSession('${s.id}')">
                    <div class="session-title">${escapeHtml(s.title || '未命名对话')}</div>
                    <div class="session-meta">${s.message_count} 条消息</div>
                    <button class="session-delete" onclick="event.stopPropagation(); deleteSession('${s.id}')">×</button>
                </div>
            `).join('');
        } else {
            sessionListEl.innerHTML = '<div class="process-empty" style="padding:20px 0">暂无对话</div>';
        }
    } catch (e) {
        sessionListEl.innerHTML = '<div class="process-empty" style="padding:20px 0">加载失败</div>';
    }
}

// 切换会话
function switchSession(sessionId) {
    browserSessionId = sessionId;
    localStorage.setItem('browser_session_id', browserSessionId);
    loadChatHistory();
    loadSessionList();
    processLog.innerHTML = '<div class="process-empty">中间过程将在这里实时显示</div>';
    traceReport.innerHTML = '<div class="process-empty">追踪报告将在对话后显示</div>';
}

// 删除会话
async function deleteSession(sessionId) {
    if (!confirm('确定删除这个对话吗？')) return;
    await fetch(`/history/${sessionId}`, { method: 'DELETE' });
    if (sessionId === browserSessionId) {
        // 删的是当前会话，自动切到新会话
        newChat();
    }
    loadSessionList();
}

// 新建对话
function newChat() {
    // 不删旧会话，只生成新 session
    browserSessionId = 'sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    localStorage.setItem('browser_session_id', browserSessionId);
    messagesEl.innerHTML = `
        <div class="msg system">
            <div class="bubble">你好！我是智能图书助手，可以帮你找书、推荐书、上架新书。试试说"推荐一本科幻小说"或"上架一本书"。</div>
        </div>`;
    processLog.innerHTML = '<div class="process-empty">中间过程将在这里实时显示</div>';
    traceReport.innerHTML = '<div class="process-empty">追踪报告将在对话后显示</div>';
    loadSessionList();
}

// 显示确认对话框
function showConfirmDialog(confirmId, detail, fields) {
    const div = document.createElement('div');
    div.className = 'msg assistant';
    div.id = `confirm-${confirmId}`;

    let fieldsHtml = '';
    if (fields && Object.keys(fields).length > 0) {
        // 可编辑字段模式
        fieldsHtml = '<div class="confirm-fields">';
        for (const [label, value] of Object.entries(fields)) {
            fieldsHtml += `
                <div class="confirm-field-row">
                    <label class="confirm-field-label">${escapeHtml(label)}</label>
                    <input type="text" class="confirm-field-input"
                           data-field="${escapeHtml(label)}"
                           value="${escapeHtml(value)}" />
                </div>
            `;
        }
        fieldsHtml += '</div>';
    } else {
        // 纯文本模式
        fieldsHtml = `<div class="confirm-detail">${escapeHtml(detail)}</div>`;
    }

    div.innerHTML = `
        <div class="bubble confirm-card">
            <div class="confirm-title">⚠️ 请确认以下信息，可修改后确认</div>
            ${fieldsHtml}
            <div class="confirm-actions">
                <button class="btn-confirm-yes" onclick="respondConfirm('${confirmId}', true)">确认上架</button>
                <button class="btn-confirm-no" onclick="respondConfirm('${confirmId}', false)">取消</button>
            </div>
        </div>
    `;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

// 响应确认
async function respondConfirm(confirmId, confirmed) {
    const card = document.getElementById(`confirm-${confirmId}`);
    let modifications = {};

    // 收集可编辑字段的值
    if (card && confirmed) {
        const inputs = card.querySelectorAll('.confirm-field-input');
        inputs.forEach(input => {
            const field = input.getAttribute('data-field');
            const value = input.value.trim();
            if (field && value) {
                modifications[field] = value;
            }
        });
    }

    // 禁用按钮和输入框
    if (card) {
        const buttons = card.querySelectorAll('button');
        buttons.forEach(b => b.disabled = true);
        const inputs = card.querySelectorAll('input');
        inputs.forEach(i => i.disabled = true);
        const resultText = confirmed ? '✅ 已确认' : '❌ 已取消';
        card.querySelector('.confirm-actions').innerHTML = `<span class="confirm-result">${resultText}</span>`;
    }
    // 通知后端（LangGraph interrupt 恢复需要 session_id）
    await fetch('/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: browserSessionId, confirmed: confirmed, modifications: modifications }),
    });
}
