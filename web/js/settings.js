/* 设置页：提供商 / 模型 / 工具限制 / MCP / 技能与提示词 / 账号 */

let cfg = null;

document.getElementById('tabs').onclick = function (e) {
  const btn = e.target.closest('button');
  if (!btn) return;
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b === btn));
  document.querySelectorAll('.page > div[id^="panel-"]').forEach(function (p) {
    p.style.display = p.id === 'panel-' + btn.dataset.tab ? 'block' : 'none';
  });
};

document.getElementById('logout').onclick = async function () {
  await api('/api/auth/logout', { body: {} });
  location.href = '/';
};

function markSaved(text) {
  const node = document.getElementById('saveState');
  node.textContent = text || '已保存 ' + now();
}

async function reload() {
  cfg = await api('/api/config');
  paintAll();
}

function paintAll() {
  paintProviders();
  paintModel();
  paintLimits();
  paintTools();
  paintMcp();
  paintParams();
  paintSys();
}

/* ---------- 提供商 ---------- */
function paintProviders() {
  const box = document.getElementById('provList');
  box.innerHTML = '';
  const list = cfg.providers || [];
  document.getElementById('provCount').textContent = list.length;
  if (!list.length) { box.innerHTML = '<div class="empty">还没有配置任何提供商</div>'; }
  list.forEach(function (p) {
    const row = el('div', 'list-row');
    row.appendChild(el('span', 'grow'));
    const g = row.lastChild;
    g.appendChild(el('div', 'nm', p.name + (p.id === cfg.ai.active_provider_id ? ' · 使用中' : '')));
    g.appendChild(el('div', 'sub2', p.base_url));
    const edit = el('button', 'ghost', '编辑');
    edit.onclick = function () {
      document.getElementById('fId').value = p.id;
      document.getElementById('fName').value = p.name;
      document.getElementById('fBase').value = p.base_url;
      document.getElementById('fKey').value = '';
      document.getElementById('fKey').placeholder = p.has_api_key ? '已保存（留空表示不修改）' : 'sk-...';
      document.getElementById('fHeaders').value = p.headers && Object.keys(p.headers).length ? JSON.stringify(p.headers) : '';
    };
    const del = el('button', 'danger', '删除');
    del.onclick = async function () {
      if (!confirm('确认删除提供商 ' + p.name + ' ?')) return;
      await api('/api/providers/' + p.id, { method: 'DELETE' });
      await reload();
    };
    row.appendChild(edit); row.appendChild(del);
    box.appendChild(row);
  });

  const sel = document.getElementById('mProv');
  sel.innerHTML = '';
  list.forEach(function (p) {
    const opt = document.createElement('option');
    opt.value = p.id; opt.textContent = p.name;
    if (p.id === cfg.ai.active_provider_id) opt.selected = true;
    sel.appendChild(opt);
  });
  paintModelList((cfg.providers.find(p => p.id === cfg.ai.active_provider_id) || {}).models || []);
}

document.getElementById('resetForm').onclick = function () {
  ['fId', 'fName', 'fBase', 'fKey', 'fHeaders'].forEach(id => document.getElementById(id).value = '');
};

document.getElementById('saveProvider').onclick = async function () {
  try {
    const payload = {
      name: document.getElementById('fName').value.trim(),
      base_url: document.getElementById('fBase').value.trim(),
      api_key: document.getElementById('fKey').value.trim(),
      headers: document.getElementById('fHeaders').value.trim() ? JSON.parse(document.getElementById('fHeaders').value) : {}
    };
    const id = document.getElementById('fId').value.trim();
    if (id) payload.id = id;
    await api('/api/providers', { body: payload });
    document.getElementById('resetForm').click();
    await reload();
    markSaved('提供商已保存');
    toast('已保存', 'ok');
  } catch (err) { toast(err.message, 'err'); }
};

document.getElementById('testBtn').onclick = async function () {
  const id = document.getElementById('fId').value.trim();
  const active = cfg.providers.find(p => p.id === (id || cfg.ai.active_provider_id));
  const pid = id || cfg.ai.active_provider_id;
  if (!pid) return toast('请先保存一个提供商', 'err');
  this.disabled = true;
  try {
    const payload = { base_url: document.getElementById('fBase').value.trim() || (active || {}).base_url };
    const key = document.getElementById('fKey').value.trim();
    if (key) payload.api_key = key;
    const res = await api('/api/providers/' + pid + '/test', { body: payload });
    toast('连通正常，' + res.count + ' 个模型，耗时 ' + res.elapsed_ms + 'ms', 'ok');
  } catch (err) { toast(err.message, 'err'); }
  finally { this.disabled = false; }
};

/* ---------- 模型 ---------- */
let allModels = [];

function paintModelList(models) {
  allModels = models || [];
  const box = document.getElementById('mList');
  const keyword = (document.getElementById('mSearch').value || '').toLowerCase();
  box.innerHTML = '';
  const list = allModels.filter(m => !keyword || m.id.toLowerCase().indexOf(keyword) !== -1);
  if (!list.length) { box.innerHTML = '<div class="empty">没有匹配的模型</div>'; return; }
  list.forEach(function (m) {
    const label = el('label');
    const input = document.createElement('input');
    input.type = 'radio'; input.name = 'm'; input.value = m.id;
    if (m.id === cfg.ai.active_model) input.checked = true;
    label.appendChild(input);
    label.appendChild(el('span', null, m.id));
    box.appendChild(label);
  });
}

function paintModel() {
  const p = cfg.providers.find(x => x.id === cfg.ai.active_provider_id) || {};
  document.getElementById('mHint').textContent = '当前默认模型：' + (cfg.ai.active_model || '未设置');
  paintModelList(p.models || []);
}

document.getElementById('mSearch').oninput = function () { paintModelList(allModels); };

document.getElementById('fetchModels').onclick = async function () {
  const pid = document.getElementById('mProv').value;
  if (!pid) return toast('请先添加一个提供商', 'err');
  this.disabled = true;
  try {
    const res = await api('/api/providers/' + pid + '/models', { body: {} });
    await reload();
    document.getElementById('mProv').value = pid;
    toast('获取到 ' + res.count + ' 个模型', 'ok');
  } catch (err) { toast(err.message, 'err'); }
  finally { this.disabled = false; }
};

document.getElementById('saveModel').onclick = async function () {
  const picked = document.querySelector('input[name="m"]:checked');
  if (!picked) return toast('请先选择模型', 'err');
  try {
    await api('/api/providers/' + document.getElementById('mProv').value + '/select', { body: { model: picked.value } });
    await reload();
    markSaved('默认模型已更新');
    toast('已设为默认模型', 'ok');
  } catch (err) { toast(err.message, 'err'); }
};

function paintParams() {
  document.getElementById('pMaxTokens').value = cfg.ai.max_tokens || '';
  document.getElementById('pTemp').value = cfg.ai.temperature ?? '';
  document.getElementById('pTimeout').value = cfg.ai.timeout || '';
}

document.getElementById('saveParams').onclick = async function () {
  await api('/api/config', { method: 'PUT', body: { ai: {
    max_tokens: Number(document.getElementById('pMaxTokens').value) || 8192,
    temperature: Number(document.getElementById('pTemp').value),
    timeout: Number(document.getElementById('pTimeout').value) || 180
  } } });
  await reload();
  markSaved('生成参数已保存');
  toast('已保存', 'ok');
};

/* ---------- 工具与限制 ---------- */
const splitList = v => String(v || '').split(',').map(s => s.trim()).filter(Boolean);

function paintLimits() {
  const l = cfg.tool_limits || {};
  document.getElementById('tEnabled').value = l.enabled === false ? '0' : '1';
  document.getElementById('tRound').value = l.max_calls_per_round || 10;
  document.getElementById('tTotal').value = l.max_total_calls || 60;
  document.getElementById('tRounds').value = l.max_rounds || 25;
  document.getElementById('tAllowed').value = (l.allowed_tools || []).join(',');
  document.getElementById('tDenied').value = (l.denied_tools || []).join(',');
  document.getElementById('tConfirm').value = (l.require_confirmation || []).join(',');
}

document.getElementById('saveLimits').onclick = async function () {
  await api('/api/config', { method: 'PUT', body: { tool_limits: {
    enabled: document.getElementById('tEnabled').value === '1',
    max_calls_per_round: Number(document.getElementById('tRound').value) || 10,
    max_total_calls: Number(document.getElementById('tTotal').value) || 60,
    max_rounds: Number(document.getElementById('tRounds').value) || 25,
    allowed_tools: splitList(document.getElementById('tAllowed').value),
    denied_tools: splitList(document.getElementById('tDenied').value),
    require_confirmation: splitList(document.getElementById('tConfirm').value)
  } } });
  await reload();
  markSaved('工具限制已保存（后端已热加载）');
  toast('已保存并立即生效', 'ok');
};

function paintTools() {
  const box = document.getElementById('toolList');
  box.innerHTML = '';
  fetch('/api/tools').then(r => r.json()).then(function (res) {
    const tools = res.tools || [];
    document.getElementById('toolCount').textContent = tools.length;
    if (!tools.length) { box.innerHTML = '<div class="empty">tools/ 目录下没有可用工具</div>'; return; }
    tools.forEach(function (t) {
      const row = el('div', 'list-row');
      const g = el('div', 'grow');
      g.appendChild(el('div', 'nm', t.name + (t.dangerous ? ' ⚠️' : '')));
      g.appendChild(el('div', 'sub2', t.description || ''));
      row.appendChild(g);
      const doc = el('button', 'ghost', '查看文档');
      doc.onclick = async function () {
        const res = await api('/api/tools/' + encodeURIComponent(t.name) + '/doc');
        alert(res.doc);
      };
      row.appendChild(doc);
      box.appendChild(row);
    });
  });
}

document.getElementById('reloadTools').onclick = async function () {
  await api('/api/tools/refresh', { body: {} });
  paintTools();
  toast('已重新扫描 tools 目录', 'ok');
};

/* ---------- MCP ---------- */
function paintMcp() {
  const box = document.getElementById('mcpList');
  box.innerHTML = '';
  const list = cfg.mcp_servers || [];
  if (!list.length) { box.innerHTML = '<div class="empty">还没有配置 MCP 服务器</div>'; return; }
  list.forEach(function (s, idx) {
    const row = el('div', 'list-row');
    const g = el('div', 'grow');
    g.appendChild(el('div', 'nm', s.name || '(未命名)'));
    g.appendChild(el('div', 'sub2', [s.command].concat(s.args || []).join(' ')));
    row.appendChild(g);
    const tog = el('button', 'ghost', s.enabled === false ? '启用' : '停用');
    tog.onclick = async function () {
      s.enabled = s.enabled === false;
      await api('/api/config', { method: 'PUT', body: { mcp_servers: list } });
      await reload();
    };
    const del = el('button', 'danger', '删除');
    del.onclick = async function () {
      list.splice(idx, 1);
      await api('/api/config', { method: 'PUT', body: { mcp_servers: list } });
      await reload();
    };
    row.appendChild(tog); row.appendChild(del);
    box.appendChild(row);
  });
}

document.getElementById('clearServer').onclick = function () {
  ['sName', 'sCmd', 'sArgs', 'sEnv', 'sCwd'].forEach(id => document.getElementById(id).value = '');
};

document.getElementById('saveServer').onclick = async function () {
  try {
    const list = (cfg.mcp_servers || []).slice();
    const item = {
      id: 'mcp_' + Math.random().toString(36).slice(2, 8),
      name: document.getElementById('sName').value.trim(),
      command: document.getElementById('sCmd').value.trim(),
      args: document.getElementById('sArgs').value.trim() ? JSON.parse(document.getElementById('sArgs').value) : [],
      env: document.getElementById('sEnv').value.trim() ? JSON.parse(document.getElementById('sEnv').value) : {},
      cwd: document.getElementById('sCwd').value.trim(),
      enabled: true
    };
    if (!item.name || !item.command) throw new Error('名称与命令必填');
    list.push(item);
    await api('/api/config', { method: 'PUT', body: { mcp_servers: list } });
    document.getElementById('clearServer').click();
    await reload();
    toast('已保存，刷新连接后生效', 'ok');
  } catch (err) { toast(err.message, 'err'); }
};

document.getElementById('refreshMcp').onclick = async function () {
  try {
    const res = await api('/api/mcp/refresh', { body: {} });
    (res.status || []).forEach(function (s) {
      toast(s.name + '：' + (s.connected ? ('已连接，' + s.tools + ' 个工具') : ('失败 - ' + (s.error || '未知'))),
        s.connected ? 'ok' : 'err');
    });
    if (!(res.status || []).length) toast('没有启用的 MCP 服务器', 'err');
  } catch (err) { toast(err.message, 'err'); }
};

/* ---------- 技能与提示词 ---------- */
function paintSkills() {
  const box = document.getElementById('skillList');
  box.innerHTML = '';
  fetch('/api/skills').then(r => r.json()).then(function (res) {
    const skills = res.skills || [];
    if (!skills.length) { box.innerHTML = '<div class="empty">skills/ 目录下还没有技能，放一个 .md 即可</div>'; return; }
    skills.forEach(function (s) {
      const row = el('div', 'list-row');
      const g = el('div', 'grow');
      g.appendChild(el('div', 'nm', s.name));
      g.appendChild(el('div', 'sub2', s.description || ''));
      row.appendChild(g);
      const view = el('button', 'ghost', '查看');
      view.onclick = function () { alert(s.content); };
      row.appendChild(view);
      box.appendChild(row);
    });
  });
}

async function paintPrompt() {
  const res = await api('/api/prompt');
  document.getElementById('promptBox').value = res.prompt;
  document.getElementById('promptInfo').textContent =
    '共 ' + res.chars + ' 字符 · 内置工具 ' + res.tools + ' 个（含所有 tools.md 与 skills）';
}

document.getElementById('refreshPrompt').onclick = async function () {
  await paintPrompt();
  toast('提示词已重新生成', 'ok');
};

/* ---------- 账号 ---------- */
document.getElementById('savePass').onclick = async function () {
  try {
    await api('/api/auth/password', { body: {
      old_password: document.getElementById('oldPass').value,
      new_password: document.getElementById('newPass').value
    } });
    document.getElementById('oldPass').value = '';
    document.getElementById('newPass').value = '';
    toast('密码已更新', 'ok');
  } catch (err) { toast(err.message, 'err'); }
};

async function paintSys() {
  const res = await api('/api/health');
  document.getElementById('sysInfo').innerHTML =
    '工作区：' + escapeHtml(res.workspace) + '<br>已加载工具：' + res.tools +
    ' 个<br>配置文件：config.json（启动与修改时自动读取）';
}

document.querySelector('#tabs').addEventListener('click', function () {
  if (document.querySelector('#tabs .on').dataset.tab === 'prompt') {
    paintSkills(); paintPrompt().catch(err => toast(err.message, 'err'));
  }
});

reload().catch(err => toast(err.message, 'err'));

