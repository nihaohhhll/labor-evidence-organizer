/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Uploaded evidence is served by the backend; the frontend only links to it.
  images: { unoptimized: true },
};

module.exports = nextConfig;
