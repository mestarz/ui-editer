import React, { useEffect, useState, useCallback, useRef } from 'react';
import Editor from '@monaco-editor/react';
import { api } from './api.js';

const DEFAULT_LUA = `-- 全局可用：vg (NVGcontext), WIDTH, HEIGHT, DPR, ASSETS_DIR
-- 'default' 字体已预加载

nvgFontFace(vg, "default")

-- 渐变背景
local g = nvgLinearGradient(vg, 0, 0, 0, HEIGHT,
  nvgRGB(60, 80, 120), nvgRGB(20, 30, 50))
nvgBeginPath(vg); nvgRect(vg, 0, 0, WIDTH, HEIGHT)
nvgFillPaint(vg, g); nvgFill(vg)

-- 圆角矩形 + 描边
nvgBeginPath(vg); nvgRoundedRect(vg, 60, 60, WIDTH-120, HEIGHT-120, 16)
nvgFillColor(vg, nvgRGBA(255, 255, 255, 30)); nvgFill(vg)
nvgStrokeColor(vg, nvgRGB(255, 255, 255)); nvgStrokeWidth(vg, 2); nvgStroke(vg)

-- 文字
nvgFontSize(vg, 32)
nvgFillColor(vg, nvgRGB(255, 255, 255))
nvgTextAlign(vg, NVG_ALIGN_CENTER + NVG_ALIGN_MIDDLE)
nvgText(vg, WIDTH/2, HEIGHT/2, "NanoVG + Lua")
`;

export default function App() {
  const [cases, setCases] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [draft, setDraft] = useState(null); // { name, lua, width, height, dpr }
  const [imgUrl, setImgUrl] = useState(null);
  const [err, setErr] = useState('');
  const [log, setLog] = useState('');
  const [busy, setBusy] = useState(false);
  const lastUrl = useRef(null);

  const refreshList = useCallback(async () => {
    setCases(await api.list());
  }, []);

  useEffect(() => { refreshList(); }, [refreshList]);

  const open = useCallback(async (id) => {
    const c = await api.get(id);
    setActiveId(id);
    setDraft({ name: c.name, lua: c.lua, width: c.width, height: c.height, dpr: c.dpr });
  }, []);

  const newCase = useCallback(async () => {
    const name = prompt('用例名称?');
    if (!name) return;
    const c = await api.create({ name, lua: DEFAULT_LUA, width: 512, height: 512, dpr: 1 });
    await refreshList();
    open(c.id);
  }, [refreshList, open]);

  const save = useCallback(async () => {
    if (!activeId || !draft) return;
    await api.update(activeId, draft);
    await refreshList();
  }, [activeId, draft, refreshList]);

  const remove = useCallback(async () => {
    if (!activeId) return;
    if (!confirm('确认删除该用例？')) return;
    await api.remove(activeId);
    setActiveId(null); setDraft(null);
    await refreshList();
  }, [activeId, refreshList]);

  const render = useCallback(async () => {
    if (!draft) return;
    setBusy(true); setErr(''); setLog('');
    const res = await api.render({ lua: draft.lua, width: draft.width, height: draft.height, dpr: draft.dpr });
    setBusy(false);
    if (res.error) {
      setErr(res.error);
      setLog(res.log || '');
      return;
    }
    if (lastUrl.current) URL.revokeObjectURL(lastUrl.current);
    lastUrl.current = res.url;
    setImgUrl(res.url);
    setLog(res.log || '');
  }, [draft]);

  // Cmd/Ctrl+S to save+render
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        save().then(render);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [save, render]);

  const update = (k, v) => setDraft(d => ({ ...d, [k]: v }));

  return (
    <div className="app">
      <aside className="sidebar">
        <header>
          <h2>用例 ({cases.length})</h2>
          <button onClick={newCase}>＋</button>
        </header>
        <ul>
          {cases.map(c => (
            <li key={c.id} className={c.id === activeId ? 'active' : ''} onClick={() => open(c.id)}>
              <div>{c.name}</div>
              <div className="meta">{c.width}×{c.height} · {new Date(c.updatedAt).toLocaleString()}</div>
            </li>
          ))}
        </ul>
      </aside>

      <section className="editor-pane">
        <div className="toolbar">
          {draft ? (
            <>
              <input type="text" value={draft.name} onChange={e => update('name', e.target.value)} style={{ width: 180 }} />
              <label>W <input type="number" value={draft.width}  onChange={e => update('width',  +e.target.value)} /></label>
              <label>H <input type="number" value={draft.height} onChange={e => update('height', +e.target.value)} /></label>
              <label>DPR <input type="number" step="0.5" value={draft.dpr} onChange={e => update('dpr', +e.target.value)} /></label>
              <span className="spacer" />
              <button onClick={save}>保存</button>
              <button onClick={render} disabled={busy}>{busy ? '渲染中…' : '渲染 (Ctrl+S)'}</button>
              <button className="danger" onClick={remove}>删除</button>
            </>
          ) : <span style={{ color: '#888' }}>左侧选择或新建用例</span>}
        </div>
        <div className="editor-host">
          {draft && (
            <Editor
              language="lua"
              theme="vs-dark"
              value={draft.lua}
              onChange={v => update('lua', v ?? '')}
              options={{ minimap: { enabled: false }, fontSize: 13, scrollBeyondLastLine: false }}
            />
          )}
        </div>
        {err && <div className="error-box">渲染错误：{err}{log ? '\n\n' + log : ''}</div>}
      </section>

      <section className="preview-pane">
        <div className="toolbar">
          <span style={{ color: '#888' }}>预览</span>
          <span className="spacer" />
          {imgUrl && draft && <span style={{ fontSize: 12, color: '#aaa' }}>{draft.width}×{draft.height} @ {draft.dpr}x</span>}
        </div>
        <div className="preview-host">
          {imgUrl ? <img src={imgUrl} alt="render" /> : <span style={{ color: '#666' }}>{draft ? '点击渲染' : ''}</span>}
        </div>
        {log && !err && <div className="status">{log.trim().split('\n').slice(0, 4).join(' · ')}</div>}
      </section>
    </div>
  );
}
