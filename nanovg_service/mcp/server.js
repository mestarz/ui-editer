#!/usr/bin/env node
// MCP server exposing the nanovg renderer + case store as tools.
// Self-contained: directly spawns the C renderer binary and reads/writes
// the cases/ folder. No HTTP server required.
//
// Configure in your AI client (e.g. Claude Code / Copilot CLI) like:
//   { "mcpServers": {
//       "nanovg": {
//         "command": "node",
//         "args": ["/abs/path/to/nanovg_service/mcp/server.js"]
//       }
//   }}
// Optional env vars (auto-detected from script location otherwise):
//   NVG_BIN     - path to nvg_renderer binary
//   NVG_CASES   - cases directory
//   NVG_ASSETS  - assets directory
//   NVG_FONT    - default font ttf

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { CaseStore } from '../server/store.js';
import { Renderer } from '../server/render.js';
import { diffPngs } from '../server/diff.js';
import { listSections, getSection, query as queryDocs } from '../server/api_docs.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const BIN    = process.env.NVG_BIN    || path.join(ROOT, 'renderer/build/nvg_renderer');
const CASES  = process.env.NVG_CASES  || path.join(ROOT, 'cases');
const ASSETS = process.env.NVG_ASSETS || path.join(ROOT, 'assets');
const FONT   = process.env.NVG_FONT   || path.join(ROOT, 'fonts/DejaVuSans.ttf');
const DOCS   = process.env.NVG_API_DOCS || '/root/workspace/game/BaiSiYeShou/docs/nanovg-api.md';

if (!fs.existsSync(BIN)) {
  console.error(`[nanovg-mcp] renderer binary not found: ${BIN}`);
  console.error(`[nanovg-mcp] build it first: cd ${ROOT} && ./build.sh`);
  process.exit(1);
}

const store = new CaseStore(CASES);
await store.init();
const renderer = new Renderer({ binPath: BIN, assetsDir: ASSETS, defaultFont: FONT });

const tools = [
  {
    name: 'nvg_render',
    description:
      'Render a Lua snippet using the TapTap-compatible NanoVG API and return a PNG image. ' +
      'The Lua script runs between nvgBeginFrame/EndFrame; globals available: vg (NVGcontext), WIDTH, HEIGHT, DPR, T (time in seconds), ASSETS_DIR, all nvg* functions and NVG_* constants. ' +
      'A "default" font is preloaded. Use this to preview UI before writing it into the game source.',
    inputSchema: {
      type: 'object',
      properties: {
        lua:    { type: 'string',  description: 'Lua source code to execute.' },
        width:  { type: 'integer', description: 'Canvas width in pixels.',  default: 512, minimum: 1, maximum: 4096 },
        height: { type: 'integer', description: 'Canvas height in pixels.', default: 512, minimum: 1, maximum: 4096 },
        dpr:    { type: 'number',  description: 'Device pixel ratio for super-sampling.', default: 1, minimum: 0.5, maximum: 4 },
        time:   { type: 'number',  description: 'Time in seconds, exposed to Lua as global T.', default: 0 },
      },
      required: ['lua'],
    },
  },
  {
    name: 'nvg_lint',
    description:
      'Validate a Lua script: runs it in a tiny 4x4 canvas and reports syntax / runtime / API errors without returning the image. ' +
      'Cheaper than nvg_render and useful as a fast self-check after editing code.',
    inputSchema: {
      type: 'object',
      properties: { lua: { type: 'string' } },
      required: ['lua'],
    },
  },
  {
    name: 'nvg_render_animation',
    description:
      'Render a sequence of frames over time. The Lua script is re-executed for each frame with a different value of the global T (seconds). ' +
      'Returns up to `frames` image content items in order. Useful for previewing animations / transitions.',
    inputSchema: {
      type: 'object',
      properties: {
        lua:    { type: 'string' },
        width:  { type: 'integer', default: 256, minimum: 1, maximum: 2048 },
        height: { type: 'integer', default: 256, minimum: 1, maximum: 2048 },
        dpr:    { type: 'number',  default: 1, minimum: 0.5, maximum: 4 },
        frames: { type: 'integer', description: 'Number of frames to render.', default: 8, minimum: 1, maximum: 32 },
        fps:    { type: 'number',  description: 'Frames per second (controls T spacing = 1/fps).', default: 8, minimum: 1, maximum: 60 },
      },
      required: ['lua'],
    },
  },
  {
    name: 'nvg_diff',
    description:
      'Render two Lua scripts at the same dimensions and return a pixel-difference highlight PNG ' +
      '(red where they differ, dimmed grayscale of A elsewhere) plus stats (changedPixels, changedRatio, maxDelta, meanDelta). ' +
      'Useful for visual regression checks.',
    inputSchema: {
      type: 'object',
      properties: {
        luaA:   { type: 'string' },
        luaB:   { type: 'string' },
        width:  { type: 'integer', default: 256, minimum: 1, maximum: 2048 },
        height: { type: 'integer', default: 256, minimum: 1, maximum: 2048 },
        dpr:    { type: 'number',  default: 1, minimum: 0.5, maximum: 4 },
        threshold: { type: 'integer', description: 'Per-pixel max-channel delta below which pixels are considered equal.', default: 0, minimum: 0, maximum: 255 },
      },
      required: ['luaA', 'luaB'],
    },
  },
  {
    name: 'nvg_list_cases',
    description: 'List all stored Lua test cases (id, name, dimensions, updatedAt).',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'nvg_get_case',
    description: 'Get a single case including its Lua source.',
    inputSchema: {
      type: 'object',
      properties: { id: { type: 'string' } },
      required: ['id'],
    },
  },
  {
    name: 'nvg_save_case',
    description:
      'Save a Lua case to the case library. If id is omitted a new case is created and the new id is returned. ' +
      'If id is provided the existing case is updated.',
    inputSchema: {
      type: 'object',
      properties: {
        id:     { type: 'string',  description: 'Existing case id (omit to create new).' },
        name:   { type: 'string',  description: 'Human-readable name (required when creating).' },
        lua:    { type: 'string' },
        width:  { type: 'integer', default: 512 },
        height: { type: 'integer', default: 512 },
        dpr:    { type: 'number',  default: 1 },
        tags:   { type: 'array', items: { type: 'string' } },
      },
    },
  },
  {
    name: 'nvg_delete_case',
    description: 'Delete a stored case by id.',
    inputSchema: {
      type: 'object',
      properties: { id: { type: 'string' } },
      required: ['id'],
    },
  },
  {
    name: 'nvg_api_docs',
    description:
      'Look up the TapTap NanoVG Lua API reference. Three modes: ' +
      '(1) no args → list all section titles; ' +
      '(2) `section` → return the full content of one section (e.g. "颜色", "路径", "文本渲染"); ' +
      '(3) `query` → fuzzy search for a function name or keyword across all sections (e.g. "nvgRect", "linear gradient", "TextAlign"). ' +
      'Use this whenever you are unsure of a function signature or constant name before writing Lua.',
    inputSchema: {
      type: 'object',
      properties: {
        query:   { type: 'string', description: 'Substring to search for (case-insensitive).' },
        section: { type: 'string', description: 'Exact or partial section title to fetch in full.' },
      },
    },
  },
];

const server = new Server(
  { name: 'nanovg-service', version: '0.1.0' },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools }));

const ok    = (text) => ({ content: [{ type: 'text', text }] });
const fail  = (text) => ({ content: [{ type: 'text', text }], isError: true });
const json  = (obj)  => ok(JSON.stringify(obj, null, 2));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args = {} } = req.params;
  try {
    switch (name) {
      case 'nvg_render': {
        const { lua, width = 512, height = 512, dpr = 1, time = 0 } = args;
        if (typeof lua !== 'string') return fail('lua must be a string');
        const { png, stderr } = await renderer.render({ lua, width, height, dpr, time });
        const content = [{
          type: 'image',
          data: png.toString('base64'),
          mimeType: 'image/png',
        }];
        if (stderr && stderr.trim()) {
          content.push({ type: 'text', text: `renderer log:\n${stderr.trim()}` });
        } else {
          content.push({ type: 'text', text: `rendered ${width}x${height} @ ${dpr}x t=${time} (${png.length} bytes)` });
        }
        return { content };
      }
      case 'nvg_lint': {
        const { lua } = args;
        if (typeof lua !== 'string') return fail('lua must be a string');
        try {
          await renderer.render({ lua, width: 4, height: 4, dpr: 1 });
          return ok('ok');
        } catch (e) {
          return fail(`lint failed: ${e.stderr ? e.stderr.trim() : e.message}`);
        }
      }
      case 'nvg_render_animation': {
        const { lua, width = 256, height = 256, dpr = 1, frames = 8, fps = 8 } = args;
        if (typeof lua !== 'string') return fail('lua must be a string');
        const content = [];
        const dt = 1 / fps;
        for (let i = 0; i < frames; i++) {
          const t = i * dt;
          const { png } = await renderer.render({ lua, width, height, dpr, time: t });
          content.push({
            type: 'image',
            data: png.toString('base64'),
            mimeType: 'image/png',
          });
        }
        content.push({ type: 'text', text: `rendered ${frames} frames @ ${fps}fps (T=0..${((frames - 1) * dt).toFixed(3)}s)` });
        return { content };
      }
      case 'nvg_diff': {
        const { luaA, luaB, width = 256, height = 256, dpr = 1, threshold = 0 } = args;
        if (typeof luaA !== 'string' || typeof luaB !== 'string') return fail('luaA and luaB must be strings');
        const [a, b] = await Promise.all([
          renderer.render({ lua: luaA, width, height, dpr }),
          renderer.render({ lua: luaB, width, height, dpr }),
        ]);
        const r = diffPngs(a.png, b.png, { threshold });
        return {
          content: [
            { type: 'image', data: r.diffPng.toString('base64'), mimeType: 'image/png' },
            { type: 'text', text: JSON.stringify({
                width: r.width, height: r.height,
                changedPixels: r.changedPixels,
                changedRatio: +r.changedRatio.toFixed(6),
                maxDelta: r.maxDelta,
                meanDelta: +r.meanDelta.toFixed(4),
                threshold,
              }, null, 2) },
          ],
        };
      }
      case 'nvg_list_cases':
        return json(await store.list());
      case 'nvg_get_case':
        return json(await store.get(args.id));
      case 'nvg_save_case': {
        if (args.id) return json(await store.update(args.id, args));
        if (!args.name) return fail('name is required when creating a new case');
        return json(await store.create(args));
      }
      case 'nvg_delete_case':
        await store.remove(args.id);
        return ok(`deleted ${args.id}`);
      case 'nvg_api_docs': {
        if (!fs.existsSync(DOCS)) {
          return fail(`api docs not found at ${DOCS} (set NVG_API_DOCS env var)`);
        }
        if (args.section) {
          const out = getSection(DOCS, args.section);
          if (!out) return fail(`section not found: ${args.section}`);
          return ok(out);
        }
        if (args.query) {
          const hits = queryDocs(DOCS, args.query);
          if (hits.length === 0) return ok(`no matches for: ${args.query}`);
          const md = hits.slice(0, 10).map(h =>
            `### ${h.section}  (${h.hits} match${h.hits > 1 ? 'es' : ''})\n\n${h.snippet}`
          ).join('\n\n---\n\n');
          return ok(md);
        }
        // No args → list sections.
        const titles = listSections(DOCS);
        return ok(`Available sections (use \`section\` to fetch one, \`query\` to search):\n` +
          titles.map(t => `- ${t}`).join('\n'));
      }
      default:
        return fail(`unknown tool: ${name}`);
    }
  } catch (e) {
    return fail(`${name} failed: ${e.message}${e.stderr ? '\n' + e.stderr : ''}`);
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);
console.error('[nanovg-mcp] ready (stdio)');
