// A stand-in for GitHub Pages, for bench.py: HTTP/2 over TLS, gzip,
// Cache-Control: max-age (600, as Pages sends, or MAX_AGE), ETags and 304s,
// and /foo served from foo.html. It serves the directory named in ROOT_FILE,
// read again on every request, so a run can "deploy" by naming another.
//
//   node pages.mjs ROOT_FILE PORT CERT_DIR   (CERT_DIR holds key.pem and cert.pem)
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, statSync } from 'node:fs';
import http2 from 'node:http2';
import path from 'node:path';
import { gzipSync } from 'node:zlib';

const [rootFile, port, certDir] = process.argv.slice(2);
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json',
  '.webmanifest': 'application/manifest+json', '.png': 'image/png', '.svg': 'image/svg+xml', '.jpg': 'image/jpeg',
  '.mid': 'audio/midi', '.xml': 'application/xml', '.css': 'text/css',
};
const files = new Map();
function load(file) {
  const mtime = statSync(file).mtimeMs;
  let f = files.get(file);
  if (!f || f.mtime !== mtime) {
    const raw = readFileSync(file), type = TYPES[path.extname(file)] || 'application/octet-stream';
    const gz = /text|json|xml|svg|javascript|manifest/.test(type) ? gzipSync(raw, { level: 6 }) : null;
    f = { mtime, raw, gz, type, etag: `"${createHash('sha1').update(raw).digest('hex').slice(0, 16)}"`, modified: new Date(mtime).toUTCString() };
    files.set(file, f);
  }
  return f;
}
const server = http2.createSecureServer({ key: readFileSync(path.join(certDir, 'key.pem')), cert: readFileSync(path.join(certDir, 'cert.pem')), allowHTTP1: true });
server.on('request', (req, res) => {
  const dir = readFileSync(rootFile, 'utf8').trim();
  let p = decodeURIComponent(new URL(req.url, 'https://x').pathname);
  if (p.endsWith('/')) p += 'index.html';
  let file = path.join(dir, p);
  if (!existsSync(file) && existsSync(`${file}.html`)) file += '.html';
  if (!existsSync(file) || statSync(file).isDirectory()) {
    res.writeHead(404);
    res.end('not found');
    return;
  }
  const f = load(file);
  const headers = { 'content-type': f.type, 'cache-control': `max-age=${process.env.MAX_AGE || '600'}`, etag: f.etag, 'last-modified': f.modified, vary: 'Accept-Encoding' };
  if (req.headers['if-none-match'] === f.etag) {
    res.writeHead(304, headers);
    res.end();
    return;
  }
  const gz = f.gz && /gzip/.test(req.headers['accept-encoding'] || '');
  if (gz) headers['content-encoding'] = 'gzip';
  res.writeHead(200, headers);
  res.end(gz ? f.gz : f.raw);
});
server.listen(Number(port), () => console.log(`serving on https://localhost:${port}`));
