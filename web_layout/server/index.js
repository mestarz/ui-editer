// ============================================================
// server/index.js  Express 入口
// ============================================================
import express from 'express';
import cors from 'cors';
import fs from 'node:fs';
import path from 'node:path';
import * as L from './lua-runtime.js';

const app = express();
app.use(cors());
app.use(express.json({ limit: '4mb' }));

// 启动时 boot Lua（一次性）
console.log('[server] booting Lua game...');
try {
  L.init();
} catch (e) {
  console.error('[server] Lua init failed:', e);
  process.exit(1);
}

app.get('/api/health', (_req, res) => res.json({ ok: true }));

app.post('/api/reload', (_req, res) => {
  try {
    console.log('[server] reload requested — re-booting Lua...');
    L.reload();
    res.json({ ok: true });
  } catch (e) {
    console.error('[server] reload failed:', e);
    res.status(500).json({ error: String(e.message || e) });
  }
});

app.get('/api/source', (req, res) => {
  const file = String(req.query.file || '');
  const line = parseInt(req.query.line || '0', 10);
  const ctx  = Math.min(20, parseInt(req.query.ctx || '4', 10));
  // 安全：只允许 scripts/ 内
  if (!file.startsWith('scripts/') || file.includes('..')) {
    return res.status(400).json({ error: 'invalid file path' });
  }
  try {
    const GAME_ROOT = path.resolve(process.env.GAME_ROOT || path.join(process.cwd(), '../../BaiSiYeShou'));
    const abs = path.resolve(GAME_ROOT, file);
    if (!abs.startsWith(GAME_ROOT + path.sep)) {
      return res.status(400).json({ error: 'path escapes game root' });
    }
    const lines = fs.readFileSync(abs, 'utf-8').split('\n');
    const from = Math.max(1, line - ctx);
    const to   = Math.min(lines.length, line + ctx);
    const out = [];
    for (let i = from; i <= to; i++) out.push({ n: i, t: lines[i - 1] });
    res.json({ file, line, lines: out });
  } catch (e) {
    res.status(404).json({ error: String(e.message || e) });
  }
});

app.get('/api/scenes', (_req, res) => {
  res.json({ scenes: L.list_scenes() });
});

app.get('/api/record/:scene', (req, res) => {
  try {
    L.reset_recorder();
    L.set_enabled(false);
    L.goto_scene(req.params.scene);
    L.set_enabled(true);
    L.fire_render();
    L.set_enabled(false);
    const events = L.get_events();
    res.json({ scene: req.params.scene, events });
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
});

const PORT = 3001;
app.listen(PORT, () => console.log(`[server] http://localhost:${PORT}`));
