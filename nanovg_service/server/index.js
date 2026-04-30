import express from 'express';
import cors from 'cors';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { CaseStore } from './store.js';
import { Renderer } from './render.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const PORT = parseInt(process.env.PORT || '3002', 10);
const BIN  = process.env.NVG_BIN || path.join(ROOT, 'renderer/build/nvg_renderer');
const ASSETS = process.env.NVG_ASSETS || path.join(ROOT, 'assets');
const FONT = process.env.NVG_FONT || path.join(ROOT, 'fonts/DejaVuSans.ttf');
const CASES = process.env.NVG_CASES || path.join(ROOT, 'cases');

if (!fs.existsSync(BIN)) {
  console.error(`[nvg-service] renderer binary missing: ${BIN}\n  build it with: cd renderer && cmake -B build && cmake --build build -j`);
}

const store = new CaseStore(CASES);
await store.init();

const renderer = new Renderer({ binPath: BIN, assetsDir: ASSETS, defaultFont: FONT });

const app = express();
app.use(cors());
app.use(express.json({ limit: '2mb' }));

app.get('/api/health', (_req, res) => res.json({ ok: true, bin: BIN, hasBin: fs.existsSync(BIN) }));

// --- cases ---
app.get('/api/cases', async (_req, res, next) => {
  try { res.json(await store.list()); } catch (e) { next(e); }
});
app.get('/api/cases/:id', async (req, res, next) => {
  try { res.json(await store.get(req.params.id)); } catch (e) { res.status(404).json({ error: e.message }); }
});
app.post('/api/cases', async (req, res, next) => {
  try { res.status(201).json(await store.create(req.body || {})); } catch (e) { res.status(400).json({ error: e.message }); }
});
app.put('/api/cases/:id', async (req, res, next) => {
  try { res.json(await store.update(req.params.id, req.body || {})); } catch (e) { res.status(404).json({ error: e.message }); }
});
app.delete('/api/cases/:id', async (req, res, next) => {
  try { await store.remove(req.params.id); res.status(204).end(); } catch (e) { next(e); }
});

// --- render ---
app.post('/api/render', async (req, res) => {
  const { lua = '', width = 512, height = 512, dpr = 1 } = req.body || {};
  if (typeof lua !== 'string') return res.status(400).json({ error: 'lua must be string' });
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0)
    return res.status(400).json({ error: 'invalid width/height' });
  try {
    const { png, stderr } = await renderer.render({ lua, width, height, dpr });
    res.set('Content-Type', 'image/png');
    if (stderr) res.set('X-Renderer-Log', encodeURIComponent(stderr.slice(0, 1024)));
    res.send(png);
  } catch (e) {
    res.status(422).json({ error: e.message, stderr: e.stderr || '' });
  }
});

// serve built UI in production
const dist = path.join(ROOT, 'dist');
if (fs.existsSync(dist)) {
  app.use(express.static(dist));
  app.get('*', (_req, res) => res.sendFile(path.join(dist, 'index.html')));
}

app.listen(PORT, () => {
  console.log(`[nvg-service] listening on http://localhost:${PORT}`);
  console.log(`  bin    = ${BIN}`);
  console.log(`  cases  = ${CASES}`);
  console.log(`  assets = ${ASSETS}`);
  console.log(`  font   = ${FONT}`);
});
