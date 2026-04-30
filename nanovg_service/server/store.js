// File-system store for Lua test cases.
// Layout: cases/<id>.lua + cases/<id>.json (metadata).
// id is a slug derived from the name plus a short random suffix.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

export class CaseStore {
  constructor(dir) { this.dir = dir; }

  async init() { await fs.mkdir(this.dir, { recursive: true }); }

  static slug(name) {
    return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'case';
  }

  async list() {
    const files = await fs.readdir(this.dir);
    const ids = files.filter(f => f.endsWith('.json')).map(f => f.slice(0, -5));
    const out = [];
    for (const id of ids) {
      try {
        const meta = JSON.parse(await fs.readFile(path.join(this.dir, id + '.json'), 'utf8'));
        out.push({ id, ...meta });
      } catch { /* skip corrupt */ }
    }
    out.sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''));
    return out;
  }

  async get(id) {
    const meta = JSON.parse(await fs.readFile(path.join(this.dir, id + '.json'), 'utf8'));
    const lua = await fs.readFile(path.join(this.dir, id + '.lua'), 'utf8');
    return { id, ...meta, lua };
  }

  async create({ name, lua = '', width = 512, height = 512, dpr = 1, tags = [] }) {
    if (!name) throw new Error('name required');
    const id = `${CaseStore.slug(name)}-${crypto.randomBytes(3).toString('hex')}`;
    const now = new Date().toISOString();
    const meta = { name, width, height, dpr, tags, createdAt: now, updatedAt: now };
    await fs.writeFile(path.join(this.dir, id + '.json'), JSON.stringify(meta, null, 2));
    await fs.writeFile(path.join(this.dir, id + '.lua'), lua);
    return { id, ...meta, lua };
  }

  async update(id, patch) {
    const cur = await this.get(id);
    const next = { ...cur, ...patch, updatedAt: new Date().toISOString() };
    const { lua, ...meta } = next;
    delete meta.id;
    await fs.writeFile(path.join(this.dir, id + '.json'), JSON.stringify(meta, null, 2));
    await fs.writeFile(path.join(this.dir, id + '.lua'), lua ?? cur.lua);
    return next;
  }

  async remove(id) {
    await fs.rm(path.join(this.dir, id + '.json'), { force: true });
    await fs.rm(path.join(this.dir, id + '.lua'), { force: true });
  }
}
