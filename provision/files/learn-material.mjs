#!/usr/bin/env node
import { createReadStream } from 'node:fs';
import { realpath, stat } from 'node:fs/promises';
import { createServer } from 'node:http';
import { homedir } from 'node:os';
import { extname, relative, resolve, sep } from 'node:path';

const origin = 'http://127.0.0.1:43180';
const root = await realpath(resolve(homedir(), 'learn/materials'));
const types = new Map([
  ['.pdf', 'application/pdf'],
  ['.png', 'image/png'],
  ['.jpg', 'image/jpeg'],
  ['.jpeg', 'image/jpeg'],
  ['.webp', 'image/webp'],
]);

async function material(path) {
  const file = await realpath(resolve(root, path));
  const type = types.get(extname(file).toLowerCase());
  if (!file.startsWith(root + sep) || !type) throw new Error('教材のパスを確認してください');
  const info = await stat(file);
  if (!info.isFile()) throw new Error('教材ファイルを指定してください');
  return { file, type, size: info.size };
}

function byteRange(header, size) {
  const match = /^bytes=(\d*)-(\d*)$/.exec(header);
  if (!match || size === 0) return null;
  const [, first, last] = match;
  const start = first ? Number(first) : Math.max(0, size - Number(last));
  const end = first && last ? Math.min(size - 1, Number(last)) : size - 1;
  return start <= end ? { start, end } : null;
}

async function serve(request, response) {
  const reply = (status, headers) => response.writeHead(status, headers).end();
  if (request.headers.host !== new URL(origin).host) return reply(403);
  if (request.method !== 'GET' && request.method !== 'HEAD') return reply(405);
  if (request.url === '/health') return reply(204);
  if (!request.url.startsWith('/materials/')) return reply(404);
  const encodedPath = request.url.slice('/materials/'.length).split('?')[0];
  let entry;
  try {
    entry = await material(decodeURIComponent(encodedPath));
  } catch {
    return reply(404);
  }
  const { file, type, size } = entry;
  const headers = {
    'Content-Type': type,
    'X-Content-Type-Options': 'nosniff',
    'Cache-Control': 'no-store',
    'Accept-Ranges': 'bytes',
  };
  const range = request.headers.range ? byteRange(request.headers.range, size) : null;
  if (request.headers.range && !range) {
    return reply(416, { 'Content-Range': `bytes */${size}` });
  }
  if (range) headers['Content-Range'] = `bytes ${range.start}-${range.end}/${size}`;
  headers['Content-Length'] = range ? range.end - range.start + 1 : size;
  const status = range ? 206 : 200;
  if (request.method === 'HEAD') return reply(status, headers);
  response.writeHead(status, headers);
  const stream = createReadStream(file, range || {});
  response.on('close', () => stream.destroy());
  stream.on('error', () => response.destroy());
  stream.pipe(response);
}

if (process.argv[2] === '--serve') {
  createServer(serve).listen(43180, '127.0.0.1');
} else {
  const [, , path, page, extra] = process.argv;
  try {
    if (!path || extra !== undefined || (page !== undefined && !/^[1-9]\d*$/.test(page))) {
      throw new Error('使い方: learn-material <教材のパス> [PDFページ番号]');
    }
    const { file, type } = await material(path);
    if (page && type !== 'application/pdf') throw new Error('ページ番号は PDF で指定できます');
    const encoded = relative(root, file).split(sep).map(encodeURIComponent).join('/');
    const fragment = page ? `#page=${page}` : '';
    console.log(`${origin}/materials/${encoded}${fragment}`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
