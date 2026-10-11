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

function renderDiff(diff) {
  return String(diff || '').split('\n').map(function (line) {
    const cls = line.startsWith('+++') || line.startsWith('---') ? 'diff-meta'
      : line.startsWith('+') ? 'diff-add'
        : line.startsWith('-') ? 'diff-del' : '';
    return '<span class="' + cls + '">' + escapeHtml(line) + '</span>';
  }).join('\n');
}
