/**
 * Prefix-rewriting reverse proxy for the Next.js frontend behind code-server.
 *
 * Why: HF Spaces exposes the workspace through code-server (:7860), which
 * proxies "/proxy/<port>/" to localhost:<port> but STRIPS that prefix before
 * forwarding. Next.js emits absolute asset URLs ("/_next/..."), so through
 * code-server the browser requests them at the host root, where code-server
 * (not Next.js) answers -> JS 404s -> the root route's client-side redirect
 * ("正在跳转…") never runs.
 *
 * Fix (same pattern as the OpenClaw Control UI proxy): Next.js runs on an
 * internal port with `basePath=/proxy/3001`. This proxy listens on :3001,
 * re-adds the prefix code-server stripped, and forwards to Next.js on :3002.
 * Because Next.js owns the basePath, every asset URL and client-side
 * navigation it emits already carries /proxy/3001 — no body rewriting needed.
 *
 * Browser flow:
 *   /proxy/3001/cases -> code-server strips -> :3001 /cases
 *     -> this proxy -> :3002 /proxy/3001/cases -> Next.js (basePath match)
 *   HTML assets "/proxy/3001/_next/..." -> code-server strips -> :3001
 *     -> this proxy -> :3002 /proxy/3001/_next/... -> Next.js
 *
 * The API stays on :8000. The proxied Next.js instance (:3002) is started
 * with NEXT_PUBLIC_API_BASE_URL=/proxy/8000/api/v1, so browser fetches go
 * to https://<space>/proxy/8000/... — same origin as the page, so no CORS.
 * code-server routes /proxy/8000/* straight to the backend. Locally
 * (dev server :3000) the default BASE_URL http://127.0.0.1:8000/api/v1
 * hits the backend directly (CORS already allows localhost:3000).
 */

import http from "node:http";

const EXTERNAL_PREFIX = "/proxy/3001"; // what the browser uses (code-server strips it)
const UPSTREAM = { host: "127.0.0.1", port: 3002 };
const LISTEN_PORT = 3001;

const server = http.createServer((req, res) => {
  const incoming = req.url || "/";
  // Re-add the prefix code-server stripped. Never double-prefix.
  // Map bare "/" to EXTERNAL_PREFIX (no trailing slash): Next.js with
  // basePath 308-redirects "/proxy/3001/" → "/proxy/3001", and code-server
  // naively prepends the prefix to the Location header, producing
  // "/proxy/3001/proxy/3001". Serving the no-slash form directly avoids it.
  const targetPath = incoming.startsWith(EXTERNAL_PREFIX)
    ? incoming
    : EXTERNAL_PREFIX + (incoming === "/" ? "" : incoming);

  const headers = { ...req.headers, host: `${UPSTREAM.host}:${UPSTREAM.port}` };
  const proxyReq = http.request(
    { hostname: UPSTREAM.host, port: UPSTREAM.port, path: targetPath, method: req.method, headers },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
      proxyRes.pipe(res);
    },
  );
  proxyReq.on("error", (err) => {
    console.error(`proxy error ${req.method} ${incoming} -> ${targetPath}:`, err.message);
    if (!res.headersSent) {
      res.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
    }
    res.end("Bad gateway (frontend proxy)");
  });
  req.pipe(proxyReq);
});

// Next.js dev HMR uses WebSockets; forward upgrades so hot reload still works.
server.on("upgrade", (req, socket, head) => {
  const incoming = req.url || "/";
  const targetPath = incoming.startsWith(EXTERNAL_PREFIX)
    ? incoming
    : EXTERNAL_PREFIX + incoming;
  const proxyReq = http.request({
    hostname: UPSTREAM.host,
    port: UPSTREAM.port,
    path: targetPath,
    method: req.method,
    headers: { ...req.headers, host: `${UPSTREAM.host}:${UPSTREAM.port}` },
  });
  proxyReq.on("upgrade", (proxyRes, proxySocket, proxyHead) => {
    const lines = [`HTTP/1.1 101 Switching Protocols`];
    for (const [k, v] of Object.entries(proxyRes.headers)) {
      lines.push(`${k}: ${v}`);
    }
    socket.write(lines.join("\r\n") + "\r\n\r\n");
    if (proxyHead?.length) socket.write(proxyHead);
    proxySocket.pipe(socket);
    socket.pipe(proxySocket);
  });
  proxyReq.on("error", () => socket.destroy());
  proxyReq.end();
});

server.listen(LISTEN_PORT, () => {
  console.log(
    `frontend prefix proxy: :${LISTEN_PORT} -> :${UPSTREAM.port}${EXTERNAL_PREFIX} (via /proxy/3001/)`,
  );
});
