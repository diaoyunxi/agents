/* 设置页：提供商 / 模型 / 工具限制 / MCP / 技能与提示词 / 账号 */

let cfg = null;

document.getElementById('tabs').onclick = function (e) {
  const btn = e.target.closest('button');
  if (!btn) return;
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b === btn));
  document.querySelectorAll('.settings-content > div[id^="panel-"]').forEach(function (p) {
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
  paintCustomCfg();
  paintMcp();
  paintCustomPrompts();
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
    const isActive = p.id === cfg.ai.active_provider_id;
    const row = el('div', 'list-row' + (isActive ? ' active' : ''));
    const g = el('div', 'grow');
    row.appendChild(g);
    g.appendChild(el('div', 'nm', p.name + (isActive ? ' · 使用中' : '')));
    g.appendChild(el('div', 'sub2', p.base_url));
    if (isActive) row.insertBefore(el('span', 'badge green', '默认'), g);
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
}

/* ---------- 模型 ---------- */
function modelsOf(pid) {
  const p = (cfg.providers || []).find(x => x.id === pid);
  return (p && p.models) || [];
}

/* 始终按「当前在 mProv 中选中的提供商」渲染模型列表，而不是写死 active_provider */
function syncModelList() {
  paintModelList(modelsOf(document.getElementById('mProv').value));
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
const MODEL_TYPE_LABELS = {
  text_to_image: '文生图', image_to_text: '图生文', image_classification: '图像分类',
  text_classification: '文本分类', translation: '翻译', text_generation: '文本生成',
  text_to_speech: '语音合成', automatic_speech_recognition: '语音识别',
  voice_activity_detection: '语音活动检测', text_embedding: '文本嵌入'
};

function modelTypeOf(m, pid) {
  pid = pid || document.getElementById('mProv').value;
  const p = (cfg.providers || []).find(x => x.id === pid);
  const overrides = (p && p.model_type_overrides) || {};
  if (m.id in overrides) return overrides[m.id];
  return m.type || 'text_generation';
}

function paintModelList(models) {
  allModels = models || [];
  const pid = document.getElementById('mProv').value;
  const p = (cfg.providers || []).find(x => x.id === pid);
  const overrides = (p && p.model_type_overrides) || {};
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
    const t = modelTypeOf(m);
    const manual = m.id in overrides;
    const badge = el('span', 'badge type-badge' + (manual ? ' manual' : ''),
      (MODEL_TYPE_LABELS[t] || t) + (manual ? '（手动）' : ''));
    badge.title = '模型类型：' + t + '（点击可手动修改）';
    badge.style.cursor = 'pointer';
    badge.onclick = function () { changeModelType(m.id, t); };
    label.appendChild(badge);
    box.appendChild(label);
  });
}

async function changeModelType(modelId, currentType) {
  const pid = document.getElementById('mProv').value;
  const p = (cfg.providers || []).find(x => x.id === pid);
  const overrides = (p && p.model_type_overrides) || {};
  const options = Object.keys(MODEL_TYPE_LABELS).map(k => k).join('\n');
  const sel = prompt('选择「' + modelId + '」的模型类型（留空=自动识别）：\n' +
    Object.keys(MODEL_TYPE_LABELS).map((k, i) => (i + 1) + '. ' + MODEL_TYPE_LABELS[k] + ' (' + k + ')').join('\n') +
    '\n\n输入序号 1-' + Object.keys(MODEL_TYPE_LABELS).length + '，或留空清除手动设置');
  if (sel === null) return;
  const idx = parseInt(sel, 10);
  let next = '';
  if (!isNaN(idx) && idx >= 1 && idx <= Object.keys(MODEL_TYPE_LABELS).length) {
    next = Object.keys(MODEL_TYPE_LABELS)[idx - 1];
  }
  try {
    await api('/api/providers/' + pid + '/models/type', { body: { model: modelId, type: next } });
    await reload();
    document.getElementById('mProv').value = pid;
    syncModelList();
    toast(next ? ('类型已设为 ' + (MODEL_TYPE_LABELS[next] || next)) : '已恢复自动识别', 'ok');
  } catch (err) { toast(err.message, 'err'); }
}

function paintModel() {
  document.getElementById('mHint').textContent = '当前默认模型：' + (cfg.ai.active_model || '未设置');
  syncModelList();
}

document.getElementById('mSearch').oninput = function () { paintModelList(allModels); };

/* 在「模型与默认」页手动切换提供商下拉框时，立即刷新对应模型列表 */
document.getElementById('mProv').onchange = function () { syncModelList(); };

document.getElementById('fetchModels').onclick = async function () {
  const pid = document.getElementById('mProv').value;
  if (!pid) return toast('请先添加一个提供商', 'err');
  this.disabled = true;
  try {
    const res = await api('/api/providers/' + pid + '/models', { body: {} });
    await reload();
    document.getElementById('mProv').value = pid;
    syncModelList();
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

/* ---------- 工具开关 ---------- */
let _toolNames = [];

function paintTools() {
  const box = document.getElementById('toolList');
  box.innerHTML = '';
  fetch('/api/tools').then(r => r.json()).then(function (res) {
    const tools = res.tools || [];
    _toolNames = tools.map(t => t.name);
    document.getElementById('toolCount').textContent = tools.length;
    if (!tools.length) { box.innerHTML = '<div class="empty">tools/ 目录下没有可用工具</div>'; return; }
    tools.forEach(function (t) {
      const row = el('div', 'list-row');
      const g = el('div', 'grow');
      g.appendChild(el('div', 'nm', t.name));
      if (t.enabled === false) g.appendChild(el('span', 'badge', '已停用'));
      if (t.dangerous) g.appendChild(el('span', 'badge orange', '高风险'));
      g.appendChild(el('div', 'sub2', t.description || ''));
      row.appendChild(g);
      const doc = el('button', 'ghost', '查看文档');
      doc.onclick = async function () {
        const res = await api('/api/tools/' + encodeURIComponent(t.name) + '/doc');
        alert(res.doc);
      };
      row.appendChild(doc);
      const enabled = t.enabled !== false;
      const tog = el('button', enabled ? 'danger' : 'ghost', enabled ? '停用' : '允许');
      tog.onclick = async function () {
        try {
          await api('/api/tools/toggle', { method: 'POST', body: { name: t.name, enabled: !enabled } });
          await reload();
          paintPrompt().catch(() => {});
          toast(t.name + (enabled ? ' 已停用' : ' 已允许') + '，提示词已更新', 'ok');
        } catch (err) { toast(err.message, 'err'); }
      };
      row.appendChild(tog);
      box.appendChild(row);
    });
  });
}

/* 批量启用/停用：通过 PUT /api/config 全量替换 tool_toggles */
async function bulkToggleTools(enabled) {
  if (!_toolNames.length) return;
  const toggles = {};
  _toolNames.forEach(n => { toggles[n] = enabled; });
  await api('/api/config', { method: 'PUT', body: { tool_toggles: toggles } });
  await reload();
  paintPrompt().catch(() => {});
  toast(enabled ? '全部工具已启用' : '全部工具已停用', 'ok');
}

document.getElementById('toggleAllOn').onclick = function () {
  bulkToggleTools(true).catch(err => toast(err.message, 'err'));
};
document.getElementById('toggleAllOff').onclick = function () {
  bulkToggleTools(false).catch(err => toast(err.message, 'err'));
};

document.getElementById('reloadTools').onclick = async function () {
  await api('/api/tools/refresh', { body: {} });
  paintTools();
  toast('已重新扫描 tools 目录', 'ok');
};

/* ---------- 自定义配置 ---------- */
let _customCfg = {};

function paintCustomCfg() {
  _customCfg = cfg.custom || {};
  const box = document.getElementById('customCfgList');
  box.innerHTML = '';
  const entries = Object.entries(_customCfg);
  if (!entries.length) {
    box.innerHTML = '<div class="empty">还没有自定义配置</div>';
    return;
  }
  entries.forEach(function ([key, val]) {
    const row = el('div', 'list-row');
    const g = el('div', 'grow');
    g.appendChild(el('div', 'nm', key));
    g.appendChild(el('div', 'sub2', JSON.stringify(val)));
    row.appendChild(g);
    const del = el('button', 'danger', '删除');
    del.onclick = async function () {
      delete _customCfg[key];
      await api('/api/tools/custom-config', { method: 'POST', body: { custom: _customCfg } });
      await reload();
      toast('已删除 ' + key, 'ok');
    };
    row.appendChild(del);
    box.appendChild(row);
  });
}

document.getElementById('ccAdd').onclick = function () {
  const key = document.getElementById('ccKey').value.trim();
  const valRaw = document.getElementById('ccVal').value.trim();
  if (!key) return toast('键不能为空', 'err');
  // 尝试解析为 JSON（数字/对象/数组），失败则按字符串处理
  let val;
  try { val = JSON.parse(valRaw); } catch (_) { val = valRaw; }
  _customCfg[key] = val;
  document.getElementById('ccKey').value = '';
  document.getElementById('ccVal').value = '';
  paintCustomCfg();
};

document.getElementById('saveCustomCfg').onclick = async function () {
  try {
    await api('/api/tools/custom-config', { method: 'POST', body: { custom: _customCfg } });
    await reload();
    markSaved('自定义配置已保存');
    toast('已保存并立即生效', 'ok');
  } catch (err) { toast(err.message, 'err'); }
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

/* ---------- 用户自定义 Prompt ---------- */
let _customPrompts = [];

function paintCustomPrompts() {
  _customPrompts = Array.isArray(cfg.custom_prompts) ? cfg.custom_prompts : [];
  renderCustomPrompts();
}

async function refreshCustomPrompts() {
  const res = await api('/api/prompts');
  _customPrompts = Array.isArray(res.prompts) ? res.prompts : [];
  cfg.custom_prompts = _customPrompts;
  renderCustomPrompts();
}

function renderCustomPrompts() {
  const box = document.getElementById('customPromptList');
  box.innerHTML = '';
  document.getElementById('customPromptCount').textContent = _customPrompts.length;
  if (!_customPrompts.length) {
    box.innerHTML = '<div class="empty">还没有自定义 Prompt，点击「添加 Prompt」创建</div>';
    return;
  }

  _customPrompts.forEach(function (p) {
    const enabled = p.enabled !== false;
    const row = el('div', 'list-row' + (enabled ? '' : ' prompt-disabled'));
    const g = el('div', 'grow');
    const title = el('div', 'prompt-title-line');
    title.appendChild(el('span', 'nm', p.name || '未命名 Prompt'));
    title.appendChild(el('span', 'badge' + (enabled ? ' green' : ''), enabled ? '已启用' : '已停用'));
    g.appendChild(title);
    g.appendChild(el('div', 'sub2 prompt-content-preview', p.content || ''));
    row.appendChild(g);

    const actions = el('div', 'prompt-actions');
    const edit = el('button', 'ghost', '编辑');
    edit.onclick = function () { openCustomPromptEditor(p); };
    actions.appendChild(edit);

    const toggle = el('button', 'ghost', enabled ? '停用' : '启用');
    toggle.onclick = async function () {
      this.disabled = true;
      try {
        await api('/api/prompts/' + encodeURIComponent(p.id), {
          method: 'PUT', body: { enabled: !enabled }
        });
        await refreshCustomPrompts();
        await paintPrompt();
        markSaved(p.name + (enabled ? ' 已停用' : ' 已启用'));
        toast(enabled ? 'Prompt 已停用' : 'Prompt 已启用', 'ok');
      } catch (err) { toast(err.message, 'err'); }
      finally { this.disabled = false; }
    };
    actions.appendChild(toggle);

    const del = el('button', 'danger', '删除');
    del.onclick = async function () {
      if (!confirm('确认删除 Prompt「' + (p.name || '未命名') + '」？此操作不可撤销。')) return;
      this.disabled = true;
      try {
        await api('/api/prompts/' + encodeURIComponent(p.id), { method: 'DELETE' });
        if (document.getElementById('cpId').value === p.id) closeCustomPromptEditor();
        await refreshCustomPrompts();
        await paintPrompt();
        markSaved('Prompt 已删除');
        toast('Prompt 已删除', 'ok');
      } catch (err) { toast(err.message, 'err'); }
      finally { this.disabled = false; }
    };
    actions.appendChild(del);
    row.appendChild(actions);
    box.appendChild(row);
  });
}

function updateCustomPromptCount() {
  document.getElementById('cpContentCount').textContent =
    document.getElementById('cpContent').value.length + ' / 20000';
}

function openCustomPromptEditor(item) {
  const editing = Boolean(item && item.id);
  document.getElementById('customPromptFormTitle').textContent = editing ? '编辑 Prompt' : '添加 Prompt';
  document.getElementById('cpId').value = editing ? item.id : '';
  document.getElementById('cpName').value = editing ? (item.name || '') : '';
  document.getElementById('cpContent').value = editing ? (item.content || '') : '';
  document.getElementById('cpEnabled').checked = editing ? item.enabled !== false : true;
  document.getElementById('customPromptEditor').style.display = 'block';
  updateCustomPromptCount();
  document.getElementById('cpName').focus();
}

function closeCustomPromptEditor() {
  document.getElementById('customPromptEditor').style.display = 'none';
  document.getElementById('cpId').value = '';
}

document.getElementById('showCustomPromptEditor').onclick = function () {
  openCustomPromptEditor(null);
};
document.getElementById('cancelCustomPrompt').onclick = closeCustomPromptEditor;
document.getElementById('cpContent').oninput = updateCustomPromptCount;

document.getElementById('saveCustomPrompt').onclick = async function () {
  const id = document.getElementById('cpId').value;
  const name = document.getElementById('cpName').value.trim();
  const content = document.getElementById('cpContent').value.trim();
  if (!name) {
    toast('请输入 Prompt 名称', 'err');
    document.getElementById('cpName').focus();
    return;
  }
  if (!content) {
    toast('请输入 Prompt 内容', 'err');
    document.getElementById('cpContent').focus();
    return;
  }

  this.disabled = true;
  try {
    await api(id ? '/api/prompts/' + encodeURIComponent(id) : '/api/prompts', {
      method: id ? 'PUT' : 'POST',
      body: { name: name, content: content, enabled: document.getElementById('cpEnabled').checked }
    });
    closeCustomPromptEditor();
    await refreshCustomPrompts();
    await paintPrompt();
    markSaved(id ? 'Prompt 已更新' : 'Prompt 已添加');
    toast(id ? 'Prompt 已更新并生效' : 'Prompt 已添加并生效', 'ok');
  } catch (err) { toast(err.message, 'err'); }
  finally { this.disabled = false; }
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
  const customCount = _customPrompts.filter(p => p.enabled !== false).length;
  document.getElementById('promptInfo').textContent =
    '共 ' + res.chars + ' 字符 · 内置工具 ' + res.tools + ' 个 · 已启用自定义 Prompt ' + customCount + ' 个';
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
    paintSkills();
    refreshCustomPrompts()
      .then(() => paintPrompt())
      .catch(err => toast(err.message, 'err'));
  }
});

reload().catch(err => toast(err.message, 'err'));

