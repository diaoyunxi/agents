/* 登录 + 新手引导 */

let state = { step: 0, providerId: '', models: [], auth: null };

async function boot() {
  state.auth = await api('/api/auth/status');
  if (state.auth.authenticated) {
    if (!state.auth.has_providers || !state.auth.active_model) {
      showWizard();
    } else {
      location.href = '/chat';
    }
  } else {
    document.getElementById('loginCard').style.display = 'block';
  }
}

function showWizard() {
  document.getElementById('loginCard').style.display = 'none';
  document.getElementById('wizardCard').style.display = 'block';
  paint();
}

document.getElementById('loginBtn').onclick = async function () {
  try {
    await api('/api/auth/login', {
      body: { username: document.getElementById('loginUser').value.trim(),
        password: document.getElementById('loginPass').value }
    });
    location.reload();
  } catch (err) { toast(err.message, 'err'); }
};

document.getElementById('loginPass').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('loginBtn').click();
});

function paint() {
  document.querySelectorAll('.step').forEach(function (node) {
    node.style.display = Number(node.dataset.step) === state.step ? 'block' : 'none';
  });
  document.querySelectorAll('#steps div').forEach(function (node, i) {
    node.className = i <= state.step ? 'on' : '';
  });
  document.getElementById('prevBtn').style.visibility = state.step === 0 ? 'hidden' : 'visible';
  document.getElementById('nextBtn').textContent =
    state.step === 4 ? '完成并进入对话' : (state.step === 2 ? '获取可用模型' : '下一步');
}

document.getElementById('prevBtn').onclick = function () {
  state.step = Math.max(0, state.step - 1); paint();
};

document.getElementById('skipBtn').onclick = function () { location.href = '/settings'; };

async function saveProvider() {
  let headers = {};
  const raw = document.getElementById('pHeaders').value.trim();
  if (raw) { try { headers = JSON.parse(raw); } catch (e) { throw new Error('自定义请求头不是合法 JSON'); } }
  const payload = {
    name: document.getElementById('pName').value.trim() || '默认服务商',
    base_url: document.getElementById('pBase').value.trim(),
    api_key: document.getElementById('pKey').value.trim(),
    headers: headers
  };
  if (!payload.base_url) throw new Error('请填写 Base URL');
  const res = await api('/api/providers', { body: payload });
  state.providerId = res.provider.id;
  return res.provider;
}

async function fetchModels() {
  const info = document.getElementById('modelInfo');
  info.innerHTML = '<span class="spinner"></span> 正在获取模型列表';
  const btn = document.getElementById('nextBtn');
  btn.disabled = true;
  try {
    const res = await api('/api/providers/' + state.providerId + '/models', { body: {} });
    state.models = res.models;
    info.innerHTML = '获取成功，共 <b>' + res.count + '</b> 个模型';
    paintModelList();
  } catch (err) {
    info.innerHTML = '<span style="color:var(--red)">获取失败：' + escapeHtml(err.message) + '</span>';
  } finally { btn.disabled = false; }
}

function paintModelList() {
  const box = document.getElementById('modelList');
  box.innerHTML = '';
  if (!state.models.length) { box.innerHTML = '<div class="empty">该服务商没有返回模型</div>'; return; }
  state.models.forEach(function (m) {
    const label = el('label');
    const input = document.createElement('input');
    input.type = 'radio'; input.name = 'model'; input.value = m.id;
    label.appendChild(input);
    label.appendChild(el('span', null, m.id));
    box.appendChild(label);
  });
}

async function finish() {
  const picked = document.querySelector('input[name="model"]:checked');
  const limits = {
    enabled: document.getElementById('limEnabled').value === '1',
    max_calls_per_round: Number(document.getElementById('limRound').value) || 10,
    max_total_calls: Number(document.getElementById('limTotal').value) || 60,
    max_rounds: Number(document.getElementById('limRounds').value) || 25,
    denied_tools: document.getElementById('limDenied').value.split(',').map(s => s.trim()).filter(Boolean),
    allowed_tools: [], require_confirmation: []
  };
  await api('/api/config', { method: 'PUT', body: { tool_limits: limits } });
  if (!picked) { toast('未选择模型，已保留默认，可在设置页修改', 'err'); return location.href = '/settings'; }
  await api('/api/providers/' + state.providerId + '/select', { body: { model: picked.value } });
  location.href = '/chat';
}

document.getElementById('nextBtn').onclick = async function () {
  const btn = this;
  btn.disabled = true;
  try {
    if (state.step === 0) {
      await saveProvider();
      state.step = 1;
    } else if (state.step === 1) {
      if (!document.getElementById('pKey').value.trim()) throw new Error('请填写 API Key');
      await api('/api/providers', { body: {
        id: state.providerId,
        name: document.getElementById('pName').value.trim() || '默认服务商',
        base_url: document.getElementById('pBase').value.trim(),
        api_key: document.getElementById('pKey').value.trim()
      } });
      state.step = 2;
    } else if (state.step === 2) {
      await fetchModels();
      state.step = 3;
    } else if (state.step === 3) {
      if (!document.querySelector('input[name="model"]:checked')) throw new Error('请先选择一个默认模型');
      state.step = 4;
    } else {
      await finish();
    }
    paint();
  } catch (err) { toast(err.message, 'err'); }
  finally { btn.disabled = false; }
};

boot().catch(err => toast(err.message, 'err'));
