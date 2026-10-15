/** @type {import("next").NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Uploaded evidence is served by the backend; the frontend only links to it.
  images: { unoptimized: true },

  // Behind HF Spaces' code-server the app is reached at /proxy/3001/ (see
  // code-server-proxy.mjs). Locally (dev server :3000, Playwright, e2e
  // scripts) NEXT_PUBLIC_BASE_PATH is unset and basePath stays empty.
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || "",

  // A second Next.js instance (:3002) serves the code-server-proxied path;
  // isolate its build cache from the local :3000 dev server.
  distDir: process.env.NEXT_DIST_DIR || ".next",

  // self-contained server bundle for the Windows portable package
  // (scripts/build-portable.sh runs `next build` and ships .next/standalone
  // next to a bundled node.exe). `next dev`/`next start` are unaffected.
  output: "standalone",
};

module.exports = nextConfig;
