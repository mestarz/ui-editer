// Spawn the C nvg_renderer subprocess and pipe lua source via stdin,
// receive PNG bytes on stdout, errors on stderr.
import { spawn } from 'node:child_process';
import path from 'node:path';

export class Renderer {
  constructor({ binPath, assetsDir, defaultFont, timeoutMs = 10000 }) {
    this.binPath = binPath;
    this.assetsDir = assetsDir;
    this.defaultFont = defaultFont;
    this.timeoutMs = timeoutMs;
  }

  render({ lua, width = 512, height = 512, dpr = 1, time = 0 }) {
    return new Promise((resolve, reject) => {
      const args = [
        '--width', String(width),
        '--height', String(height),
        '--dpr', String(dpr),
        '--assets', this.assetsDir,
        '--time', String(time),
      ];
      if (this.defaultFont) args.push('--font', this.defaultFont);

      const proc = spawn(this.binPath, args, { stdio: ['pipe', 'pipe', 'pipe'] });
      const chunks = [];
      const errChunks = [];
      let timedOut = false;
      const timer = setTimeout(() => {
        timedOut = true;
        proc.kill('SIGKILL');
      }, this.timeoutMs);

      proc.stdout.on('data', d => chunks.push(d));
      proc.stderr.on('data', d => errChunks.push(d));
      proc.on('error', err => { clearTimeout(timer); reject(err); });
      proc.on('close', code => {
        clearTimeout(timer);
        const stderr = Buffer.concat(errChunks).toString('utf8');
        if (timedOut) return reject(new Error(`renderer timeout (${this.timeoutMs}ms)`));
        if (code !== 0) {
          const err = new Error(`renderer exit ${code}: ${stderr.trim()}`);
          err.exitCode = code; err.stderr = stderr;
          return reject(err);
        }
        resolve({ png: Buffer.concat(chunks), stderr });
      });

      proc.stdin.on('error', () => { /* ignore broken pipe; surfaces via stderr */ });
      proc.stdin.end(lua);
    });
  }
}
