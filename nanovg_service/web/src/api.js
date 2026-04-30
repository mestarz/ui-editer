const J = (r) => r.ok ? r.json() : r.json().then(e => Promise.reject(new Error(e.error || r.statusText)));

export const api = {
  list:   ()       => fetch('/api/cases').then(J),
  get:    (id)     => fetch('/api/cases/' + id).then(J),
  create: (body)   => fetch('/api/cases', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(J),
  update: (id, b)  => fetch('/api/cases/' + id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }).then(J),
  remove: (id)     => fetch('/api/cases/' + id, { method: 'DELETE' }).then(r => { if (!r.ok && r.status !== 204) throw new Error('delete failed'); }),

  // Returns { url, log, error? } — url is a blob URL the caller must revoke when done.
  render: async (body) => {
    const r = await fetch('/api/render', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!r.ok) {
      const j = await r.json().catch(() => ({ error: r.statusText }));
      return { error: j.error || r.statusText, log: j.stderr || '' };
    }
    const blob = await r.blob();
    const log = decodeURIComponent(r.headers.get('X-Renderer-Log') || '');
    return { url: URL.createObjectURL(blob), log };
  },
};
