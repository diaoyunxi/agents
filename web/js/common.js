/* 公共工具：请求封装、提示、Markdown 渲染、格式化 */

async function api(path, options = {}) {
  const opts = { method: options.body ? 'POST' : 'GET', headers: {}, ...options };
  if (opts.body && typeof opts.body !== 'string') {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  const resp = await fetch(path, opts);
  let data = null;
  try { data = await resp.json(); } catch (e) { data = null; }
  if (!resp.ok) {
    const detail = (data && data.detail) || ('请求失败 ' + resp.status);
    if (resp.status === 401) location.href = '/';
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return data;
}

function toast(msg, type) {
  const node = document.createElement('div');
  node.className = 'toast ' + (type || '');
  node.textContent = msg;
  document.body.appendChild(node);
  setTimeout(function () { node.style.opacity = '0'; node.style.transition = '.4s'; }, 2600);
  setTimeout(function () { node.remove(); }, 3100);
}

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function now() {
  return new Date().toTimeString().slice(0, 8);
}

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function inline(text) {
  let out = escapeHtml(text);
  out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
  out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  out = out.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  out = out.replace(/~~([^~]+)~~/g, '<del>$1</del>');
  return out;
}

function splitRow(line) {
  let t = line.trim();
  if (t.startsWith('|')) t = t.slice(1);
  if (t.endsWith('|')) t = t.slice(0, -1);
  return t.split('|').map(c => c.trim());
}

/** 轻量 Markdown 渲染：标题 / 列表 / 表格 / 代码块 / 引用 */
function renderMarkdown(src) {
  const lines = String(src || '').split('\n');
  let html = '', inCode = false, codeLang = '', codeBuf = [], listType = null;
  const closeList = function () { if (listType) { html += '</' + listType + '>'; listType = null; } };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^\s*```/.test(line)) {
      if (!inCode) { closeList(); inCode = true; codeLang = line.replace(/^\s*```/, '').trim(); codeBuf = []; }
      else { html += '<pre><code>' + escapeHtml(codeBuf.join('\n')) + '</code></pre>'; inCode = false; }
      continue;
    }
    if (inCode) { codeBuf.push(line); continue; }

    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) { closeList(); const lv = Math.min(h[1].length, 6); html += '<h' + lv + '>' + inline(h[2]) + '</h' + lv + '>'; continue; }

    const li = line.match(/^(\s*)([-*+]|\d+\.)\s+(.*)$/);
    if (li) {
      const type = /\d/.test(li[2]) ? 'ol' : 'ul';
      if (listType !== type) { closeList(); html += '<' + type + '>'; listType = type; }
      html += '<li>' + inline(li[3]) + '</li>';
      continue;
    }
    closeList();

    if (/^\s*>\s?/.test(line)) { html += '<blockquote>' + inline(line.replace(/^\s*>\s?/, '')) + '</blockquote>'; continue; }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) { html += '<hr>'; continue; }

    if (line.indexOf('|') !== -1 && i + 1 < lines.length && /^[\s|:-]+$/.test(lines[i + 1]) && lines[i + 1].indexOf('-') !== -1) {
      const head = splitRow(line);
      html += '<table><thead><tr>' + head.map(c => '<th>' + inline(c) + '</th>').join('') + '</tr></thead><tbody>';
      i += 2;
      while (i < lines.length && lines[i].indexOf('|') !== -1 && lines[i].trim()) {
        html += '<tr>' + splitRow(lines[i]).map(c => '<td>' + inline(c) + '</td>').join('') + '</tr>';
        i++;
      }
      html += '</tbody></table>';
      i--;
      continue;
    }
    if (!line.trim()) { continue; }
    html += '<p>' + inline(line) + '</p>';
  }
  if (inCode) html += '<pre><code>' + escapeHtml(codeBuf.join('\n')) + '</code></pre>';
  closeList();
  return html;
}

/* ============================ 自更新提示 ============================
   每次访问 web 时检查远端是否有新提交，若有则在页面底部提示，
   点击「立即更新」后由后端交给独立的 updater.py 完成拉取与自我重启。 */

let _updateInfo = null;

function _ubSetText(text) {
  const node = document.getElementById('ubText');
  if (node) node.innerHTML = text;
}

function showUpdateBanner(info) {
  let banner = document.getElementById('updateBanner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'updateBanner';
    banner.className = 'update-banner';
    banner.innerHTML =
      '<div class="ub-main">' +
      '  <span class="ub-dot"></span>' +
      '  <span class="ub-text" id="ubText"></span>' +
      '  <button class="ghost" id="ubToggle">详情</button>' +
      '  <button class="accent" id="ubApply">立即更新</button>' +
      '  <button class="ghost ub-x" id="ubClose" title="关闭">×</button>' +
      '</div>' +
      '<div class="ub-commits" id="ubCommits" style="display:none"></div>';
    document.body.appendChild(banner);

    document.getElementById('ubClose').onclick = function () { banner.remove(); };
    document.getElementById('ubApply').onclick = function () { applyUpdate(); };
    document.getElementById('ubToggle').onclick = function () {
      const box = document.getElementById('ubCommits');
      const open = box.style.display === 'none';
      box.style.display = open ? 'block' : 'none';
      this.textContent = open ? '收起' : '详情';
    };
  }

  _ubSetText('发现 <b>' + info.behind + '</b> 个新提交 · ' +
    '<code>' + escapeHtml(info.local_head || '?') + '</code> → ' +
    '<code>' + escapeHtml(info.remote_head || '?') + '</code>');

  const box = document.getElementById('ubCommits');
  box.innerHTML = (info.commits || []).map(function (c) {
    return '<div class="ub-commit"><b>' + escapeHtml(c.hash) + '</b>' +
      '<span class="grow">' + escapeHtml(c.subject) + '</span>' +
      '<span class="ub-when">' + escapeHtml(c.when || '') + '</span></div>';
  }).join('') || '<div class="ub-commit">（无提交详情）</div>';
}

async function checkUpdate(force) {
  let info = null;
  const ctrl = new AbortController();
  const timer = setTimeout(function () { ctrl.abort(); }, 25000);
  try {
    const resp = await fetch('/api/update/status' + (force ? '?force=true' : ''),
      { cache: 'no-store', headers: { 'Accept': 'application/json' }, signal: ctrl.signal });
    if (!resp.ok) return null;            // 未登录或非仓库：静默忽略
    info = await resp.json();
  } catch (e) { return null; }
  finally { clearTimeout(timer); }
  _updateInfo = info;
  if (info && info.is_repo && info.has_update) {
    showUpdateBanner(info);
  } else {
    const banner = document.getElementById('updateBanner');
    if (banner) banner.remove();
  }
  return info;
}

function applyUpdate() {
  const btn = document.getElementById('ubApply');
  if (btn) { btn.disabled = true; btn.textContent = '更新中…'; }
  _ubSetText('正在拉取新代码并重启服务，页面会自动恢复…');
  fetch('/api/update/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
    cache: 'no-store'
  }).catch(function () { /* 进程退出导致请求中断，属正常现象 */ });
  waitForRestart();
}

function waitForRestart() {
  const started = Date.now();
  let seenDown = false;
  const tick = async function () {
    let alive = false;
    try {
      const resp = await fetch('/api/health', { cache: 'no-store' });
      alive = resp.ok;
    } catch (e) { alive = false; }
    if (alive && seenDown) { showUpdateResult(); return; }
    if (!alive) seenDown = true;
    if (Date.now() - started > 120000) {
      _ubSetText('服务未在预期时间内恢复，请手动重启（python main.py）');
      return;
    }
    setTimeout(tick, 1000);
  };
  setTimeout(tick, 800);
}

async function showUpdateResult() {
  let message = '更新完成，服务已重启';
  try {
    const resp = await fetch('/api/update/result', { cache: 'no-store' });
    if (resp.ok) {
      const data = await resp.json();
      if (data && data.message) message = data.message;
    }
  } catch (e) { /* 忽略 */ }
  _ubSetText(escapeHtml(message) + '，2 秒后刷新页面…');
  setTimeout(function () {
    const url = new URL(location.href);
    url.searchParams.set('_', Date.now());
    location.replace(url.toString());
  }, 2000);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function () { checkUpdate(); });
} else {
  checkUpdate();
}

function renderDiff(diff) {

  return String(diff || '').split('\n').map(function (line) {
    const cls = line.startsWith('+++') || line.startsWith('---') ? 'diff-meta'
      : line.startsWith('+') ? 'diff-add'
        : line.startsWith('-') ? 'diff-del' : '';
    return '<span class="' + cls + '">' + escapeHtml(line) + '</span>';
  }).join('\n');
}
