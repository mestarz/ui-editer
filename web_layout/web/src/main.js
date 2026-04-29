// ============================================================
// web/src/main.js  浏览器入口：场景导航 + 元素渲染 + 拖拽 + 导出
// ============================================================
import { renderElements, setupDragHandlers, getOverrides, resetOverrides, resetSelected, bindTreeFilter } from './editor.js';

const API = ''; // vite 代理 /api → :3001

let currentScene = null;
let currentEvents = [];

// ---------- 场景列表 ----------
async function loadScenes() {
  const r = await fetch(API + '/api/scenes').then(r => r.json());
  const ul = document.getElementById('scene-list');
  ul.innerHTML = '';
  for (const s of r.scenes) {
    const li = document.createElement('li');
    li.textContent = s.id;
    const badge = document.createElement('span');
    badge.className = 'badge';
    badge.textContent = s.module.split('.').pop();
    li.appendChild(badge);
    li.onclick = () => selectScene(s.id, li);
    ul.appendChild(li);
  }
}

async function selectScene(id, liEl) {
  document.querySelectorAll('#scene-list li').forEach(x => x.classList.remove('active'));
  if (liEl) liEl.classList.add('active');
  setStatus(`录制 ${id} ...`);
  try {
    const r = await fetch(API + '/api/record/' + encodeURIComponent(id)).then(r => r.json());
    if (r.error) { setStatus('错误: ' + r.error); return; }
    currentScene = id;
    currentEvents = r.events || [];
    renderElements(currentEvents, id);
    updateStats();
    setStatus(`已加载 ${id}：${currentEvents.length} 个元素`);
  } catch (e) {
    setStatus('请求失败: ' + e.message);
  }
}

function setStatus(msg) { document.getElementById('status-bar').textContent = msg; }

function updateStats() {
  const ov = getOverrides(currentScene);
  const modified = Object.keys(ov).length;
  const byType = {};
  for (const e of currentEvents) byType[e.type] = (byType[e.type] || 0) + 1;
  document.getElementById('stats').textContent =
    `场景: ${currentScene}\n元素总数: ${currentEvents.length}\n已修改: ${modified}\n类型分布:\n` +
    Object.entries(byType).map(([k, v]) => `  ${k}: ${v}`).join('\n');
}

// ---------- 选中信息 ----------
function updateSelectionInfo(items) {
  const el = document.getElementById('selection-info');
  if (!items || items.length === 0) { el.textContent = '（未选中）'; return; }
  if (items.length === 1) {
    const it = items[0];
    el.textContent =
      `id:    ${it.id}\n` +
      `type:  ${it.type} (${it.api})\n` +
      `pos:   (${it.x.toFixed(0)}, ${it.y.toFixed(0)})\n` +
      `size:  ${it.w.toFixed(0)} × ${it.h.toFixed(0)}\n` +
      `src:   ${it.src}\n` +
      (it.hint ? `hint:  ${it.hint}\n` : '') +
      (it._modified ? `\n[已修改] dx=${it.dx} dy=${it.dy} dw=${it.dw} dh=${it.dh}` : '');
  } else {
    el.textContent = `[多选] ${items.length} 个元素`;
  }
}

// ---------- 导出 ----------
async function exportFiles() {
  if (!currentScene) { alert('请先选择场景'); return; }
  const ov = getOverrides(currentScene);
  if (Object.keys(ov).length === 0) { alert('当前场景没有任何修改'); return; }

  setStatus('生成详细报告中（拉取源码上下文）...');
  const md = await buildRichMarkdown(currentScene, ov, currentEvents);
  const json = { scene: currentScene, timestamp: new Date().toISOString(), overrides: ov };
  const payload = md + '\n\n## 原始 overrides JSON\n\n```json\n' + JSON.stringify(json, null, 2) + '\n```\n';

  try {
    await navigator.clipboard.writeText(payload);
    setStatus(`✓ 已复制到剪贴板 (${Object.keys(ov).length} 项修改，${payload.length} 字符)`);
  } catch (e) {
    const ta = document.createElement('textarea');
    ta.value = payload; document.body.appendChild(ta);
    ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
    setStatus(`✓ 已复制到剪贴板 (fallback)`);
  }
}

// 拉源码上下文
async function fetchSrc(file, line, ctx = 4) {
  try {
    const r = await fetch(`${API}/api/source?file=${encodeURIComponent(file)}&line=${line}&ctx=${ctx}`).then(r => r.json());
    if (r.error) return null;
    return r.lines;
  } catch { return null; }
}

// 富 markdown：源码片段 + 同区域兄弟元素
async function buildRichMarkdown(scene, ov, events) {
  const byEvId = new Map(events.map(e => [e.id, e]));

  // 按 src 文件分组修改
  const byFile = {};
  for (const [id, m] of Object.entries(ov)) {
    const ev = byEvId.get(id);
    if (!ev) continue;
    const file = ev.src.split(':')[0];
    (byFile[file] = byFile[file] || []).push({ id, ev, m });
  }

  let md = `# Layout Overrides — \`${scene}\`\n\n`;
  md += `生成时间: ${new Date().toISOString()}\n`;
  md += `修改总数: **${Object.keys(ov).length}** 项，涉及 **${Object.keys(byFile).length}** 个源文件\n\n`;
  md += `---\n\n`;
  md += `## 给 AI 的说明\n\n`;
  md += `下面每条修改都对应主仓库 \`scripts/\` 下某个 \`Renderer.*\` 或 \`nvgImagePattern\` 调用产生的绘制矩形。\n`;
  md += `请按 **"原 (x,y,w,h) → 新 (x,y,w,h)"** 在源码该行附近找到对应硬编码常量并修改。\n\n`;
  md += `**关键提示**：\n`;
  md += `- 同一行可能多次出现（循环/列表渲染），请通过 \`occurrence\` 字段判断改第几个\n`;
  md += `- 元素位置可能由变量计算得出（如 \`x = baseX + i * gap\`），优先改 \`baseX\`/\`gap\` 而非展开循环\n`;
  md += `- "同区域兄弟元素"列出了周围未修改的元素，仅供你识别上下文，**不要动它们**\n`;
  md += `- 元素 hint 可能是文本内容、图片文件名或调用栈线索，帮助你定位\n\n`;
  md += `---\n\n`;

  for (const [file, items] of Object.entries(byFile)) {
    md += `## \`${file}\`\n\n`;

    // 同文件内所有事件（含未修改）—— 用于兄弟检测
    const allInFile = events.filter(e => e.src.split(':')[0] === file);

    for (const { id, ev, m } of items) {
      const lineNo = parseInt(ev.src.split(':')[1] || '0', 10);
      // 计算同 src（行号相同）出现序号
      const sameSrc = allInFile.filter(e => e.src === ev.src);
      const occurrence = sameSrc.findIndex(e => e.id === id) + 1;

      const ox = ev.x.toFixed(0), oy = ev.y.toFixed(0), ow = ev.w.toFixed(0), oh = ev.h.toFixed(0);
      const nx = (ev.x + (m.dx || 0)).toFixed(0);
      const ny = (ev.y + (m.dy || 0)).toFixed(0);
      const nw = (ev.w + (m.dw || 0)).toFixed(0);
      const nh = (ev.h + (m.dh || 0)).toFixed(0);

      md += `### Line ${lineNo} — \`${ev.api}\`${ev.hint ? `  *${ev.hint}*` : ''}\n\n`;
      md += `| 字段 | 值 |\n|---|---|\n`;
      md += `| 类型 | \`${ev.type}\` (\`${ev.api}\`) |\n`;
      md += `| 原矩形 | \`x=${ox}, y=${oy}, w=${ow}, h=${oh}\` |\n`;
      md += `| 新矩形 | \`x=${nx}, y=${ny}, w=${nw}, h=${nh}\` |\n`;
      md += `| 偏移 | \`dx=${m.dx||0}, dy=${m.dy||0}, dw=${m.dw||0}, dh=${m.dh||0}\` |\n`;
      md += `| 出现序号 | 该行第 ${occurrence}/${sameSrc.length} 次调用 |\n`;
      if (ev.hint) md += `| hint | \`${ev.hint}\` |\n`;
      md += `\n`;

      // 拉源码片段（上下文 ±10 行）
      const ctxLines = await fetchSrc(file, lineNo, 10);
      if (ctxLines && ctxLines.length) {
        md += `**源码上下文（±10 行）：**\n\n\`\`\`lua\n`;
        for (const ln of ctxLines) {
          const marker = ln.n === lineNo ? '>>> ' : '    ';
          md += `${marker}${String(ln.n).padStart(4, ' ')}: ${ln.t}\n`;
        }
        md += `\`\`\`\n\n`;
      }

      // 完整调用栈
      if (Array.isArray(ev.stack) && ev.stack.length) {
        md += `**调用栈（自当前帧向外，最多 8 层）：**\n\n`;
        md += `| # | 函数 | 文件:行 |\n|---|---|---|\n`;
        for (let i = 0; i < ev.stack.length; i++) {
          const fr = ev.stack[i];
          md += `| ${i} | \`${fr.name || '?'}\` | \`${fr.file}:${fr.line}\` |\n`;
        }
        md += `\n`;

        // 调用栈第二层（即 Renderer 调用方的上一层，多半是 Draw 入口）的源码片段
        const parent = ev.stack[1];
        if (parent && parent.file && parent.file.startsWith('scripts/')) {
          const pCtx = await fetchSrc(parent.file, parent.line, 6);
          if (pCtx && pCtx.length) {
            md += `**父帧 \`${parent.file}:${parent.line}\` 上下文（±6 行）：**\n\n\`\`\`lua\n`;
            for (const ln of pCtx) {
              const marker = ln.n === parent.line ? '>>> ' : '    ';
              md += `${marker}${String(ln.n).padStart(4, ' ')}: ${ln.t}\n`;
            }
            md += `\`\`\`\n\n`;
          }
        }
      }

      // 同区域兄弟元素（扩大到 ±100px，最多 12 个）
      const nearby = allInFile.filter(e => {
        if (e.id === id) return false;
        return Math.abs(e.x - ev.x) < 100 && Math.abs(e.y - ev.y) < 100;
      }).slice(0, 12);
      if (nearby.length) {
        md += `**同区域兄弟元素（±100px，未修改，仅供参考）：**\n\n`;
        md += `| api | line | x,y,w,h | hint |\n|---|---|---|---|\n`;
        for (const n of nearby) {
          const nl = n.src.split(':')[1] || '?';
          md += `| \`${n.api}\` | ${nl} | ${n.x.toFixed(0)},${n.y.toFixed(0)},${n.w.toFixed(0)},${n.h.toFixed(0)} | ${(n.hint || '').slice(0, 30)} |\n`;
        }
        md += `\n`;
      }
      md += `---\n\n`;
    }
  }
  return md;
}

// ---------- 全局事件 ----------
document.getElementById('btn-export').onclick = exportFiles;
document.getElementById('btn-reload').onclick = async () => {
  setStatus('重载 Lua 中...');
  try {
    const r = await fetch(API + '/api/reload', { method: 'POST' }).then(r => r.json());
    if (r.error) { setStatus('重载失败: ' + r.error); return; }
    setStatus('Lua 已重载');
    if (currentScene) {
      // 重新录制当前场景
      const liEl = [...document.querySelectorAll('#scene-list li')].find(x => x.textContent.startsWith(currentScene));
      await selectScene(currentScene, liEl);
    }
  } catch (e) {
    setStatus('重载失败: ' + e.message);
  }
};
document.getElementById('btn-deselect').onclick = () => setupDragHandlers.deselectAll();
document.getElementById('btn-reset').onclick = () => { resetSelected(); updateStats(); };
document.getElementById('btn-reset-all').onclick = () => {
  if (confirm('重置当前场景所有修改？')) {
    resetOverrides(currentScene);
    selectSceneRefresh();
  }
};

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') setupDragHandlers.deselectAll();
  if (e.key === 'r' || e.key === 'R') { resetSelected(); updateStats(); }
});

function selectSceneRefresh() {
  if (!currentScene) return;
  renderElements(currentEvents, currentScene);
  updateStats();
}

// 暴露给 editor.js 的回调
window.__onSelectionChange = updateSelectionInfo;
window.__onMutate = updateStats;

loadScenes().then(() => setStatus('就绪。点击左侧场景开始'));
bindTreeFilter();
