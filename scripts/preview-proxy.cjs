// پروکسی سبک برای preview: پورت 3000 (هدف پیش‌فرض gateway) → FastAPI روی 8000
const http = require('http');

const TARGET = { host: '127.0.0.1', port: 8000 };

const server = http.createServer((req, res) => {
  const proxyReq = http.request(
    { ...TARGET, path: req.url, method: req.method, headers: { ...req.headers, host: 'localhost:8000' } },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
      proxyRes.pipe(res);
    },
  );
  proxyReq.on('error', (e) => {
    res.writeHead(502, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('BPMS backend unavailable: ' + e.message);
  });
  req.pipe(proxyReq);
});

server.listen(3000, '0.0.0.0', () => console.log('BPMS preview proxy on :3000 -> :8000'));
