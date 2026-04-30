// Pixel diff between two RGBA PNG buffers. Pure JS (pngjs).
// Returns { diffPng, totalPixels, changedPixels, maxDelta, meanDelta }.
import { PNG } from 'pngjs';

function decode(buf) {
  return PNG.sync.read(buf);
}

export function diffPngs(aBuf, bBuf, { threshold = 0 } = {}) {
  const a = decode(aBuf);
  const b = decode(bBuf);
  if (a.width !== b.width || a.height !== b.height) {
    throw new Error(
      `dimension mismatch: a=${a.width}x${a.height} b=${b.width}x${b.height}`
    );
  }
  const w = a.width, h = a.height;
  const out = new PNG({ width: w, height: h });
  const dst = out.data;
  let changed = 0, sum = 0, max = 0;
  for (let i = 0; i < a.data.length; i += 4) {
    const dr = Math.abs(a.data[i]   - b.data[i]);
    const dg = Math.abs(a.data[i+1] - b.data[i+1]);
    const db = Math.abs(a.data[i+2] - b.data[i+2]);
    const da = Math.abs(a.data[i+3] - b.data[i+3]);
    const m  = Math.max(dr, dg, db, da);
    if (m > max) max = m;
    sum += m;
    if (m > threshold) {
      changed++;
      // highlight: red on diff, dim original elsewhere
      dst[i]   = 255;
      dst[i+1] = 0;
      dst[i+2] = 0;
      dst[i+3] = 255;
    } else {
      // grayscale dim of A
      const g = (a.data[i] + a.data[i+1] + a.data[i+2]) / 3 * 0.3;
      dst[i] = dst[i+1] = dst[i+2] = g | 0;
      dst[i+3] = 255;
    }
  }
  const total = w * h;
  return {
    diffPng: PNG.sync.write(out),
    totalPixels: total,
    changedPixels: changed,
    changedRatio: changed / total,
    maxDelta: max,
    meanDelta: sum / (total * 4),
    width: w,
    height: h,
  };
}
