/* 对话页：SSE 流式渲染思考 / 正文 / 工具调用，右侧汇总文件变更 */

const threadEl = document.getElementById('thread');
const threadInner = threadEl.querySelector('.thread-inner');
const changesEl = document.getElementById('changes');
const history = [];
let controller = null;
let cur = null;
let lastChangeKey = '';

/* ---------- 会话管理 ---------- */
let currentConvId = null;
let convTitle = '';
const convListEl = document.getElementById('convList');

function scrollDown() {
  threadEl.scrollTop = threadEl.scrollHeight;
}

/* ---------- 模型选择 ---------- */
async function loadModels() {
  const res = await api('/api/providers');
  const pSel = document.getElementById('providerSel');
  const mSel = document.getElementById('modelSel');
  pSel.innerHTML = '';
  (res.providers || []).forEach(function (p) {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = p.name;
    if (p.id === res.active) opt.selected = true;
    pSel.appendChild(opt);
  });
  await fillModels(res.active);
}

async function fillModels(pid) {
  if (!pid) return;
  const res = await api('/api/models?provider_id=' + encodeURIComponent(pid));
  const mSel = document.getElementById('modelSel');
  mSel.innerHTML = '';
  const models = res.models && res.models.length ? res.models : [{ id: res.model }];
  models.forEach(function (m) {
    const opt = document.createElement('option');
    opt.value = m.id;
    opt.textContent = m.name || m.id;
    if (m.id === res.model) opt.selected = true;
    mSel.appendChild(opt);
  });
}

document.getElementById('providerSel').onchange = function () { fillModels(this.value); };
document.getElementById('reloadModels').onclick = async function () {
  const pid = document.getElementById('providerSel').value;
  try {
    await api('/api/providers/' + pid + '/models', { body: {} });
    await fillModels(pid);
    toast('模型列表已更新', 'ok');
  } catch (err) { toast(err.message, 'err'); }
};

document.getElementById('logout').onclick = async function () {
  await api('/api/auth/logout', { body: {} });
  location.href = '/';
};

document.getElementById('togglePanel').onclick = function () {
  document.getElementById('panel').classList.toggle('collapsed');
};

document.getElementById('clearChanges').onclick = function () {
  changesEl.innerHTML = '<div class="empty">已清空</div>';
  lastChangeKey = '';
  document.getElementById('changeCount').textContent = '0';
  document.getElementById('sideCount').textContent = '0';
};

document.getElementById('suggestions').onclick = function (e) {
  if (e.target.classList.contains('suggestion')) {
    document.getElementById('input').value = e.target.dataset.p;
    send();
  }
};

/* ---------- 消息渲染 ---------- */
function newAssistant() {
  const turn = el('div', 'turn agent');

  const head = el('div', 'turn-head');
  head.appendChild(el('span', 'role', 'Agent'));
  const modelBadge = el('span', 'badge orange', '连接中');
  head.appendChild(modelBadge);
  head.appendChild(el('span', 'rule'));
  head.appendChild(el('span', null, now()));
  turn.appendChild(head);

  const reasoning = el('details', 'reasoning');
  reasoning.style.display = 'none';
  reasoning.appendChild(el('summary', null, '思考过程'));
  const reasonBody = el('div', 'reasoning-body');
  reasoning.appendChild(reasonBody);
  turn.appendChild(reasoning);

  const calls = el('div', 'calls');
  turn.appendChild(calls);

  const answer = el('div', 'md answer');
  turn.appendChild(answer);

  threadInner.appendChild(turn);
  scrollDown();
  return { turn, head, modelBadge, reasoning, reasonBody, calls, answer, answerCur: null,
    reasonText: '', live: '', round: 0, blocks: [], raw: '' };
}

function addToolBlock(call) {
  const box = el('div', 'call');
  const head = el('div', 'call-head');
  head.appendChild(el('span', 'tag', '工具'));
  head.appendChild(el('span', 'nm', call.tool));
  head.appendChild(el('span', 'grow'));
  const state = el('span', 'badge grey', '执行中');
  head.appendChild(state);

  const args = el('pre', 'call-body args', JSON.stringify(call.arguments || {}, null, 2));
  const out = el('pre', 'call-body');
  out.style.display = 'none';

  box.appendChild(head);
  box.appendChild(args);
  box.appendChild(out);

  head.onclick = function () {
    const open = out.style.display === 'none';
    out.style.display = open ? 'block' : 'none';
    args.style.display = open ? 'none' : 'block';
  };

  cur.calls.appendChild(box);
  scrollDown();
  const rec = { box, state, out };
  cur.blocks.push(rec);
  return rec;
}

/* ---------- 文件变更面板 ---------- */
const ACTION_LABEL = { create: '新建', modify: '修改', delete: '删除' };

function renderChanges(list) {
  const key = JSON.stringify(list.map(c => [c.path, c.action, c.time]));
  if (key === lastChangeKey) return;
  lastChangeKey = key;
  document.getElementById('changeCount').textContent = list.length;
  document.getElementById('sideCount').textContent = list.length;
  changesEl.innerHTML = '';
  if (!list.length) {
    changesEl.appendChild(el('div', 'empty', '本次会话中 AI 对文件的改动会显示在这里'));
    return;
  }
  list.forEach(function (c) {
    const box = el('div', 'change');
    const head = el('div', 'change-head');
    head.appendChild(el('span', 'badge grey', ACTION_LABEL[c.action] || c.action));
    head.appendChild(el('span', 'change-path', c.path));
    const stats = el('span', 'change-stats');
    stats.appendChild(el('span', 'plus', '+' + c.additions));
    stats.appendChild(document.createTextNode(' '));
    stats.appendChild(el('span', 'minus', '-' + c.deletions));
    head.appendChild(stats);

    const pre = document.createElement('pre');
    pre.innerHTML = renderDiff(c.diff);
    pre.style.display = 'none';

    head.onclick = function () { pre.style.display = pre.style.display === 'none' ? 'block' : 'none'; };
    box.appendChild(head);
    box.appendChild(pre);
    changesEl.appendChild(box);
  });
}

/* ---------- 对话（持久化到后端 chat/） ---------- */

function clearThread() {
  threadInner.innerHTML = '';
}

function showIntroPlaceholder() {
  clearThread();
  const turn = el('div', 'turn agent');
  const head = el('div', 'turn-head');
  head.appendChild(el('span', 'role', 'Agent'));
  head.appendChild(el('span', 'rule'));
  head.appendChild(el('span', null, '就绪'));
  turn.appendChild(head);
  const md = el('div', 'md');
  md.innerHTML = '<p>开始一段新对话，或从左栏选择已有对话继续。</p>';
  turn.appendChild(md);
  threadInner.appendChild(turn);
}

function addUserTurn(text) {
  const turn = el('div', 'turn user');
  const head = el('div', 'turn-head');
  head.appendChild(el('span', 'role', '你'));
  head.appendChild(el('span', 'rule'));
  head.appendChild(el('span', null, now()));
  turn.appendChild(head);
  turn.appendChild(el('div', 'user-text', text));
  threadInner.appendChild(turn);
  scrollDown();
}

function addAssistantTurn(content) {
  const turn = el('div', 'turn agent');
  const head = el('div', 'turn-head');
  head.appendChild(el('span', 'role', 'Agent'));
  head.appendChild(el('span', 'rule'));
  head.appendChild(el('span', null, ''));
  turn.appendChild(head);
  const body = el('div', 'md answer');
  body.innerHTML = content ? renderMarkdown(content) : '<p class="hint">（无正文输出）</p>';
  turn.appendChild(body);
  threadInner.appendChild(turn);
  scrollDown();
}

async function refreshConversationList() {
  let list = [];
  try {
    const res = await api('/api/conversations');
    list = res.conversations || [];
  } catch (err) { /* 忽略 */ }
  convListEl.innerHTML = '';
  if (!list.length) {
    convListEl.appendChild(el('div', 'empty', '还没有对话，点击「+ 新对话」开始'));
    return;
  }
  list.forEach(function (c) {
    const item = el('div', 'convo');
    item.dataset.id = c.id;
    if (c.id === currentConvId) item.classList.add('active');
    item.appendChild(el('div', 'convo-title', c.title || '新对话'));
    item.appendChild(el('div', 'convo-meta', (c.updated_at || '') + ' · ' + (c.message_count || 0) + ' 条'));
    const del = el('button', 'convo-del', '×');
    del.title = '删除对话';
    del.onclick = async function (e) {
      e.stopPropagation();
      if (!confirm('确定删除该对话？此操作不可恢复。')) return;
      try {
        await api('/api/conversations/' + c.id, { method: 'DELETE' });
        if (currentConvId === c.id) { currentConvId = null; history.length = 0; showIntroPlaceholder(); }
        await refreshConversationList();
      } catch (err) { toast(err.message, 'err'); }
    };
    item.appendChild(del);
    item.onclick = function () { loadConversationById(c.id); };
    convListEl.appendChild(item);
  });
}

async function loadConversationById(id) {
  try {
    const res = await api('/api/conversations/' + id);
    currentConvId = res.conversation.id;
    convTitle = res.conversation.title || '新对话';
    history.length = 0;
    (res.conversation.messages || []).forEach(function (m) {
      history.push({ role: m.role, content: m.content });
    });
    clearThread();
    if (!history.length) { showIntroPlaceholder(); }
    else {
      history.forEach(function (m) {
        if (m.role === 'user') addUserTurn(m.content);
        else addAssistantTurn(m.content);
      });
    }
    await refreshConversationList();
  } catch (err) { toast(err.message, 'err'); }
}

async function ensureConversation() {
  if (currentConvId) return currentConvId;
  const res = await api('/api/conversations', { body: {} });
  currentConvId = res.conversation.id;
  convTitle = res.conversation.title || '新对话';
  await refreshConversationList();
  return currentConvId;
}

function currentTitle() {
  if (convTitle && convTitle !== '新对话') return convTitle;
  const first = history.find(function (m) { return m.role === 'user'; });
  return first ? first.content.slice(0, 24) : '新对话';
}

async function saveConversation() {
  if (!currentConvId) return;
  convTitle = currentTitle();
  try {
    await api('/api/conversations/' + currentConvId, {
      method: 'PUT',
      body: { messages: history, title: convTitle },
    });
    await refreshConversationList();
  } catch (err) { /* 静默保存失败 */ }
}

document.getElementById('newChat').onclick = async function () {
  currentConvId = null;
  convTitle = '';
  history.length = 0;
  await ensureConversation();
  showIntroPlaceholder();
  document.getElementById('input').focus();
};

/* ---------- SSE 会话 ---------- */
function handle(ev) {
  switch (ev.event) {
    case 'start':
      cur.modelBadge.textContent = ev.model;
      document.getElementById('status').textContent = ev.provider + ' · ' + ev.model;
      break;
    case 'round': {
      cur.round = ev.index;
      cur.live = '';
      cur.answerCur = el('div', 'md round');
      cur.answer.appendChild(cur.answerCur);
      break;
    }
    case 'thinking': {
      cur.reasonText += ev.content;
      cur.reasoning.style.display = 'block';
      cur.reasoning.open = true;
      cur.reasonBody.textContent = cur.reasonText;
      break;
    }
    case 'delta':
      cur.live += ev.content;
      if (cur.answerCur) {
        cur.answerCur.innerHTML = '<span class="badge grey">输出中</span> ' + escapeHtml(cur.live.slice(-1500));
        scrollDown();
      }
      break;
    case 'message': {
      const text = (ev.segments || []).filter(s => s.type === 'text').map(s => s.content).join('\n');
      const target = cur.answerCur || cur.answer;
      let html = text ? renderMarkdown(text)
        : (ev.tool_calls ? '<p class="hint">（本轮仅发起工具调用）</p>' : '<p class="hint">（无正文输出）</p>');
      if (ev.parse_errors) {
        html += '<p class="hint" style="color:#b2492f">⚠ 有 ' + ev.parse_errors +
          ' 处工具调用 JSON 解析失败，未执行，已要求模型重试</p>';
      }
      target.innerHTML = html;
      cur.raw += (ev.raw || '');
      scrollDown();
      break;
    }
    case 'parse_error':
      toast('工具调用 JSON 解析失败：' + (ev.error || ''), 'err');
      break;
    case 'tool_start':
      addToolBlock(ev);
      break;
    case 'tool_end': {
      const blk = cur.blocks[cur.blocks.length - 1];
      if (blk) {
        blk.state.textContent = ev.ok ? '成功' : '失败';
        blk.state.className = 'badge ' + (ev.ok ? 'green' : 'orange');
        blk.out.textContent = ev.output || '(无输出)';
        if (!ev.ok) blk.box.classList.add('fail');
      }
      break;
    }
    case 'changes':
      renderChanges(ev.changes || []);
      break;
    case 'fallback':
      toast(ev.message, 'err');
      break;
    case 'limit':
      cur.answer.innerHTML += '<p class="hint">' + escapeHtml(ev.message) + '</p>';
      break;
    case 'stopped':
      cur.answer.innerHTML += '<p class="hint">' + escapeHtml(ev.message || '已结束') + '</p>';
      break;
    case 'error':
      cur.answer.innerHTML += '<p style="color:#b2492f">错误：' + escapeHtml(ev.message) + '</p>';
      break;
    case 'end': {
      if (ev.changes) renderChanges(ev.changes);
      const reasonText = { stopped: '模型主动结束', idle: '未推进而结束',
        max_rounds: '达到轮数上限', parse_failed: '解析失败结束',
        error: '出错结束', completed: '完成' }[ev.reason] || ev.reason || '完成';
      cur.answer.innerHTML += '<div class="hint" style="margin-top:12px">' + escapeHtml(reasonText) +
        ' · 轮次 ' + cur.round + ' · 工具调用 ' + ev.calls + ' 次 · 用时 ' +
        (ev.elapsed_ms / 1000).toFixed(1) + 's</div>';
      if (cur.raw) history.push({ role: 'assistant', content: cur.raw });
      saveConversation();
      break;
    }
  }
}

async function send() {
  const input = document.getElementById('input');
  const text = input.value.trim();
  if (!text || controller) return;
  try { await ensureConversation(); } catch (err) { /* 保存不可用时仍可对话 */ }
  input.value = '';

  const turn = el('div', 'turn user');
  const head = el('div', 'turn-head');
  head.appendChild(el('span', 'role', '你'));
  head.appendChild(el('span', 'rule'));
  head.appendChild(el('span', null, now()));
  turn.appendChild(head);
  turn.appendChild(el('div', 'user-text', text));
  threadInner.appendChild(turn);
  scrollDown();
  history.push({ role: 'user', content: text });

  cur = newAssistant();
  controller = new AbortController();
  document.getElementById('send').style.display = 'none';
  document.getElementById('stop').style.display = 'inline-block';
  document.getElementById('status').innerHTML = '<span class="spinner"></span> 生成中';

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history: history.slice(0, -1),
        provider_id: document.getElementById('providerSel').value,
        model: document.getElementById('modelSel').value
      }),
      signal: controller.signal
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '请求失败 ' + resp.status }));
      throw new Error(err.detail || '请求失败');
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      const blocks = buffer.split('\n\n');
      buffer = blocks.pop();
      for (const block of blocks) {
        const line = block.split('\n').find(l => l.startsWith('data:'));
        if (!line) continue;
        try { handle(JSON.parse(line.slice(5))); } catch (e) { /* 忽略半包 */ }
      }
    }
  } catch (err) {
    cur.answer.innerHTML += '<p style="color:#b2492f">' + escapeHtml(err.message) + '</p>';
  } finally {
    controller = null;
    cur = null;
    document.getElementById('send').style.display = 'inline-block';
    document.getElementById('stop').style.display = 'none';
    document.getElementById('status').textContent = '';
    scrollDown();
    input.focus();
  }
}

document.getElementById('send').onclick = send;
document.getElementById('stop').onclick = function () { if (controller) controller.abort(); };
document.getElementById('input').addEventListener('keydown', function (e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});

loadModels().catch(err => toast(err.message, 'err'));
refreshConversationList().catch(err => toast(err.message, 'err'));

