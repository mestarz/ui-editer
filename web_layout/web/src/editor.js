// ============================================================
// web/src/editor.js  Canvas 元素渲染 + 拖拽/缩放/多选 + overrides
// 依赖：纯 DOM，无第三方库
// ============================================================

const canvas = document.getElementById('canvas');

// 每个场景独立的 overrides
const overridesByScene = JSON.parse(localStorage.getItem('overrides') || '{}');
function saveOv() { localStorage.setItem('overrides', JSON.stringify(overridesByScene)); }

let currentScene = null;
let elements = [];        // [{ id, type, api, x, y, w, h, src, hint, _node, _modified, dx, dy, dw, dh }]
let selected = new Set(); // ids

// ---------- 稳定 ID ----------
const occCount = {};
function makeId(ev) {
  const key = `${ev.src}|${ev.api}`;
  occCount[key] = (occCount[key] || 0) + 1;
  return `${ev.src}#${ev.api}#${occCount[key]}${ev.hint ? '#' + ev.hint.slice(0, 16) : ''}`;
}

// ---------- 渲染 ----------
export function renderElements(events, sceneId) {
  currentScene = sceneId;
  canvas.innerHTML = '';
  elements = [];
  selected.clear();
  for (const k of Object.keys(occCount)) delete occCount[k];

  const ov = overridesByScene[sceneId] || {};

  // 按 depth 排序：浅层先（z-index 用顺序近似）
  const sorted = events.map((e, i) => ({ ...e, _origOrder: i })).sort((a, b) => a.depth - b.depth);

  for (const ev of sorted) {
    const id = makeId(ev);
    ev.id = id;
    const m = ov[id] || {};
    const dx = m.dx || 0, dy = m.dy || 0, dw = m.dw || 0, dh = m.dh || 0;

    // 跳过尺寸为 0 的事件（线段两端点为 x/y/w/h 时 w=h=0，难以拖拽）
    const w = ev.w + dw, h = ev.h + dh;
    if (w <= 0 || h <= 0) continue;

    const div = document.createElement('div');
    div.className = 'elem t-' + (ev.type || 'Unknown');
    if (m.dx || m.dy || m.dw || m.dh) div.classList.add('modified');
    div.style.left = (ev.x + dx) + 'px';
    div.style.top = (ev.y + dy) + 'px';
    div.style.width = w + 'px';
    div.style.height = h + 'px';
    div.dataset.id = id;

    const label = document.createElement('div');
    label.className = 'label';
    label.textContent = `${ev.api}${ev.hint ? ' "' + ev.hint.slice(0, 20) + '"' : ''}`;
    div.appendChild(label);

    canvas.appendChild(div);
    elements.push({ ...ev, _node: div, dx, dy, dw, dh, _modified: !!(m.dx||m.dy||m.dw||m.dh) });
  }

  attachInteract();
  renderTree();
}

// ---------- UI 树（按 src 文件分组） ----------
let treeFilter = '';
let treeOnlyModified = false;

function renderTree() {
  const list = document.getElementById('tree-list');
  if (!list) return;
  list.innerHTML = '';

  // 分组：src 文件名（去掉行号）
  const groups = {};
  for (const el of elements) {
    const file = (el.src || '?').split(':')[0];
    (groups[file] = groups[file] || []).push(el);
  }

  const filterLow = treeFilter.toLowerCase();
  const matches = (el) => {
    if (treeOnlyModified && !el._modified) return false;
    if (!filterLow) return true;
    return (el.api || '').toLowerCase().includes(filterLow)
      || (el.hint || '').toLowerCase().includes(filterLow)
      || (el.src || '').toLowerCase().includes(filterLow);
  };

  for (const [file, items] of Object.entries(groups)) {
    const visible = items.filter(matches);
    if (visible.length === 0) continue;

    const group = document.createElement('div');
    group.className = 'tree-group';
    const hdr = document.createElement('div');
    hdr.className = 'tree-group-hdr';
    hdr.innerHTML = `<span>${file.replace('scripts/', '')}</span><span class="count">${visible.length}/${items.length}</span>`;
    hdr.onclick = () => group.classList.toggle('collapsed');
    group.appendChild(hdr);

    const inner = document.createElement('div');
    inner.className = 'tree-items';
    for (const el of visible) {
      const row = document.createElement('div');
      row.className = `tree-item t-${el.type}`;
      if (selected.has(el.id)) row.classList.add('selected');
      if (el._modified) row.classList.add('modified');
      row.dataset.id = el.id;
      const hintTxt = el.hint || '';
      row.innerHTML =
        `<span class="api">${el.api}</span>` +
        `<span class="hint">${escapeHtml(hintTxt)}</span>` +
        `<span class="pos">${el.x.toFixed(0)},${el.y.toFixed(0)} ${el.w.toFixed(0)}×${el.h.toFixed(0)}</span>`;
      row.onclick = (e) => {
        selectId(el.id, e.shiftKey);
        // 滚动 canvas 让元素可见
        el._node.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
      };
      inner.appendChild(row);
    }
    group.appendChild(inner);
    list.appendChild(group);
  }
  if (list.children.length === 0) {
    list.innerHTML = '<div style="color:#5a6270;padding:8px;">（无匹配）</div>';
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}

// 暴露给 main.js 用于绑定过滤输入
export function bindTreeFilter() {
  const inp = document.getElementById('tree-filter');
  const cb = document.getElementById('tree-only-modified');
  if (inp) inp.oninput = (e) => { treeFilter = e.target.value; renderTree(); };
  if (cb) cb.onchange = (e) => { treeOnlyModified = e.target.checked; renderTree(); };
}

// ---------- 选择 ----------
function selectId(id, additive) {
  if (!additive) selected.clear();
  if (selected.has(id)) selected.delete(id); else selected.add(id);
  refreshSelectionVisual();
}

function refreshSelectionVisual() {
  for (const el of elements) {
    const isSel = selected.has(el.id);
    el._node.classList.toggle('selected', isSel);
    // 移除旧 handles
    el._node.querySelectorAll('.handle').forEach(h => h.remove());
    if (isSel && selected.size === 1) {
      for (const dir of ['nw','n','ne','w','e','sw','s','se']) {
        const h = document.createElement('div');
        h.className = 'handle ' + dir;
        h.dataset.dir = dir;
        el._node.appendChild(h);
      }
    }
  }
  // 同步树面板选中状态
  document.querySelectorAll('#tree-list .tree-item').forEach(row => {
    row.classList.toggle('selected', selected.has(row.dataset.id));
  });
  const items = elements.filter(e => selected.has(e.id));
  if (window.__onSelectionChange) window.__onSelectionChange(items);
}

function deselectAll() { selected.clear(); refreshSelectionVisual(); }
setupDragHandlers.deselectAll = deselectAll;

// ---------- 拖拽 / 缩放 ----------
let drag = null; // { mode: 'move'|'resize', dir, startX, startY, items: [{id, ox, oy, ow, oh}] }

function attachInteract() {
  canvas.onmousedown = (e) => {
    const handle = e.target.closest('.handle');
    const elemDiv = e.target.closest('.elem');
    if (handle && elemDiv) {
      // resize 单选
      const id = elemDiv.dataset.id;
      if (!selected.has(id)) { selected.clear(); selected.add(id); refreshSelectionVisual(); }
      startDrag(e, 'resize', handle.dataset.dir);
      e.preventDefault();
      return;
    }
    if (elemDiv) {
      const id = elemDiv.dataset.id;
      if (!selected.has(id)) selectId(id, e.shiftKey);
      else if (e.shiftKey) { selected.delete(id); refreshSelectionVisual(); return; }
      startDrag(e, 'move', null);
      e.preventDefault();
      return;
    }
    // 空白点击：取消
    deselectAll();
  };
}

function startDrag(e, mode, dir) {
  const items = elements.filter(el => selected.has(el.id)).map(el => ({
    id: el.id,
    ox: parseFloat(el._node.style.left),
    oy: parseFloat(el._node.style.top),
    ow: parseFloat(el._node.style.width),
    oh: parseFloat(el._node.style.height),
    bx: el.x, by: el.y, bw: el.w, bh: el.h, // 基线（原始事件坐标）
  }));
  drag = { mode, dir, startX: e.clientX, startY: e.clientY, items };
  window.addEventListener('mousemove', onDragMove);
  window.addEventListener('mouseup', onDragEnd);
}

function onDragMove(e) {
  if (!drag) return;
  const dx = e.clientX - drag.startX;
  const dy = e.clientY - drag.startY;
  for (const it of drag.items) {
    const el = elements.find(x => x.id === it.id);
    if (!el) continue;
    let nx = it.ox, ny = it.oy, nw = it.ow, nh = it.oh;
    if (drag.mode === 'move') {
      nx = it.ox + dx; ny = it.oy + dy;
    } else {
      const d = drag.dir;
      if (d.includes('e')) nw = Math.max(4, it.ow + dx);
      if (d.includes('s')) nh = Math.max(4, it.oh + dy);
      if (d.includes('w')) { nw = Math.max(4, it.ow - dx); nx = it.ox + (it.ow - nw); }
      if (d.includes('n')) { nh = Math.max(4, it.oh - dy); ny = it.oy + (it.oh - nh); }
    }
    el._node.style.left = nx + 'px';
    el._node.style.top = ny + 'px';
    el._node.style.width = nw + 'px';
    el._node.style.height = nh + 'px';
    el.dx = Math.round(nx - it.bx);
    el.dy = Math.round(ny - it.by);
    el.dw = Math.round(nw - it.bw);
    el.dh = Math.round(nh - it.bh);
  }
}

function onDragEnd() {
  if (!drag) return;
  // 写入 overrides
  const ov = overridesByScene[currentScene] = overridesByScene[currentScene] || {};
  for (const it of drag.items) {
    const el = elements.find(x => x.id === it.id);
    if (!el) continue;
    const m = { dx: el.dx, dy: el.dy, dw: el.dw, dh: el.dh };
    if (!m.dx && !m.dy && !m.dw && !m.dh) {
      delete ov[el.id];
      el._modified = false;
      el._node.classList.remove('modified');
    } else {
      ov[el.id] = m;
      el._modified = true;
      el._node.classList.add('modified');
    }
  }
  saveOv();
  drag = null;
  window.removeEventListener('mousemove', onDragMove);
  window.removeEventListener('mouseup', onDragEnd);
  if (window.__onMutate) window.__onMutate();
  refreshSelectionVisual();
  renderTree();
}

// ---------- 公共 API ----------
export function setupDragHandlers() {} // (函数 hoist 用，selectAll 等挂在 .deselectAll 上)
export function getOverrides(scene) { return overridesByScene[scene] || {}; }
export function resetOverrides(scene) {
  delete overridesByScene[scene]; saveOv();
}
export function resetSelected() {
  if (!currentScene || selected.size === 0) return;
  const ov = overridesByScene[currentScene] || {};
  for (const id of selected) {
    delete ov[id];
    const el = elements.find(x => x.id === id);
    if (el) {
      el.dx = el.dy = el.dw = el.dh = 0;
      el._modified = false;
      el._node.style.left = el.x + 'px';
      el._node.style.top = el.y + 'px';
      el._node.style.width = el.w + 'px';
      el._node.style.height = el.h + 'px';
      el._node.classList.remove('modified');
    }
  }
  saveOv();
  refreshSelectionVisual();
}
