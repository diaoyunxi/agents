/* 对话页：SSE 流式渲染思考 / 正文 / 工具调用，右侧汇总文件变更 */

const messagesEl = document.getElementById('messages');
const changesEl = document.getElementById('changes');
const history = [];
let controller = null;
let cur = null;
let lastChangeKey = '';

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

document.getElementById('toggleSide').onclick = function () {
  document.getElementById('side').classList.toggle('hidden');
};

document.getElementById('clearChanges').onclick = function () {
  changesEl.innerHTML = '<div class="empty">已清空</div>';
  lastChangeKey = '';
  document.getElementById('changeCount').textContent = '0';
};

document.getElementById('chips').onclick = function (e) {
  if (e.target.classList.contains('chip')) {
    document.getElementById('input').value = e.target.dataset.p;
    send();
  }
};

/* ---------- 消息渲染 ---------- */
function newAssistant() {
  const wrap = el('div', 'msg assistant');
  const who = el('div', 'who');
  who.appendChild(el('span', null, 'Agent'));
  const modelBadge = el('span', 'badge', '…');
  who.appendChild(modelBadge);
  who.appendChild(el('span', null, now()));
  wrap.appendChild(who);

  const think = el('details', 'think');
  think.appendChild(el('summary', null, '🧠 思考过程'));
  const thinkBody = el('div', 'think-body');
  think.appendChild(thinkBody);
  wrap.appendChild(think);

  const tools = el('div', 'tools');
  wrap.appendChild(tools);
  const out = el('div', 'md out');
  wrap.appendChild(out);
  messagesEl.appendChild(wrap);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return { wrap, who, modelBadge, think, thinkBody, tools, out, outCur: null,
    thinkText: '', live: '', round: 0, blocks: [], raw: '' };
}

function addToolBlock(call) {
  const box = el('div', 'tool');
  const head = el('div', 'tool-head');
  head.appendChild(el('span', null, '🔧'));
  head.appendChild(el('span', 'nm', call.tool));
  head.appendChild(el('span', 'grow'));
  const state = el('span', 'badge', '执行中');
  head.appendChild(state);
  const args = el('div', 'tool-body args', JSON.stringify(call.arguments || {}, null, 2));
  const out = el('div', 'tool-body');
  out.style.display = 'none';
  box.appendChild(head); box.appendChild(args); box.appendChild(out);
  head.onclick = function () {
    const open = out.style.display === 'none';
    out.style.display = open ? 'block' : 'none';
    args.style.display = open ? 'none' : 'block';
  };
  cur.tools.appendChild(box);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  const rec = { box, state, out };
  cur.blocks.push(rec);
  return rec;
}

/* ---------- 文件变更侧边栏 ---------- */
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
    const head = el('div', 'ch');
    head.appendChild(el('span', null, c.action === 'create' ? '🆕' : (c.action === 'delete' ? '🗑️' : '✏️')));
    head.appendChild(el('span', 'grow', c.path));
    head.appendChild(el('span', 'add', '+' + c.additions));
    head.appendChild(el('span', 'del', '-' + c.deletions));
    const pre = document.createElement('pre');
    pre.innerHTML = renderDiff(c.diff);
    pre.style.display = 'none';
    const view = el('span', 'badge', '全文');
    view.onclick = async function (ev) {
      ev.stopPropagation();
      try {
        const res = await api('/api/file?path=' + encodeURIComponent(c.path));
        pre.innerHTML = renderDiff('--- ' + c.path + ' ---\n' + res.content);
        pre.style.display = 'block';
      } catch (err) { toast(err.message, 'err'); }
    };
    head.appendChild(view);
    head.onclick = function () { pre.style.display = pre.style.display === 'none' ? 'block' : 'none'; };
    box.appendChild(head); box.appendChild(pre);
    changesEl.appendChild(box);
  });
}

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
      cur.outCur = el('div', 'md round');
      cur.out.appendChild(cur.outCur);
      break;
    }
    case 'thinking': {
      cur.thinkText += ev.content;
      cur.think.style.display = 'block';
      cur.thinkBody.textContent = cur.thinkText;
      break;
    }
    case 'delta':
      cur.live += ev.content;
      if (cur.outCur) {
        cur.outCur.innerHTML = '<span class="badge">输出中…</span> ' + escapeHtml(cur.live.slice(-1500));
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
      break;
    case 'message': {
      const text = (ev.segments || []).filter(s => s.type === 'text').map(s => s.content).join('\n');
      const target = cur.outCur || cur.out;
      target.innerHTML = text ? renderMarkdown(text)
        : (ev.tool_calls ? '<p class="hint">（本轮仅发起工具调用）</p>' : '<p class="hint">（无正文输出）</p>');
      cur.raw += (ev.raw || '');
      messagesEl.scrollTop = messagesEl.scrollHeight;
      break;
    }
    case 'tool_start':
      addToolBlock(ev);
      break;
    case 'tool_end': {
      const blk = cur.blocks[cur.blocks.length - 1];
      if (blk) {
        blk.state.textContent = ev.ok ? '成功' : '失败';
        blk.state.className = 'badge ' + (ev.ok ? 'green' : 'amber');
        blk.out.textContent = ev.output || '(无输出)';
        if (!ev.ok) blk.box.classList.add('err');
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
      cur.out.innerHTML += '<p class="hint">' + escapeHtml(ev.message) + '</p>';
      break;
    case 'error':
      cur.out.innerHTML += '<p style="color:var(--red)">错误：' + escapeHtml(ev.message) + '</p>';
      break;
    case 'end':
      if (ev.changes) renderChanges(ev.changes);
      cur.out.innerHTML += '<div class="hint" style="margin-top:10px">轮次 ' + cur.round +
        ' · 工具调用 ' + ev.calls + ' 次 · 用时 ' + (ev.elapsed_ms / 1000).toFixed(1) + 's</div>';
      if (cur.raw) history.push({ role: 'assistant', content: cur.raw });
      break;
  }
}

async function send() {
  const input = document.getElementById('input');
  const text = input.value.trim();
  if (!text || controller) return;
  input.value = '';

  const userMsg = el('div', 'msg user');
  userMsg.appendChild(el('div', 'who', '👤 我 · ' + now()));
  userMsg.appendChild(el('div', 'bubble', text));
  messagesEl.appendChild(userMsg);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  history.push({ role: 'user', content: text });

  cur = newAssistant();
  controller = new AbortController();
  document.getElementById('send').style.display = 'none';
  document.getElementById('stop').style.display = 'inline-block';
  document.getElementById('status').innerHTML = '<span class="spin"></span> 生成中…';

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
    cur.out.innerHTML += '<p style="color:var(--red)">' + escapeHtml(err.message) + '</p>';
  } finally {
    controller = null;
    cur = null;
    document.getElementById('send').style.display = 'inline-block';
    document.getElementById('stop').style.display = 'none';
    document.getElementById('status').textContent = '';
    messagesEl.scrollTop = messagesEl.scrollHeight;
    input.focus();
  }
}

document.getElementById('send').onclick = send;
document.getElementById('stop').onclick = function () { if (controller) controller.abort(); };
document.getElementById('input').addEventListener('keydown', function (e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});

loadModels().catch(err => toast(err.message, 'err'));

