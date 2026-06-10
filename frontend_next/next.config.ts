import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    // Turbopack persists its compilation cache to .next/cache on disk so
    // `npm run dev` restarts don't recompile every route from scratch.
    // Cuts cold first-hit time per route from ~5-10s to <1s on warm
    // restarts. New in Next.js 16 (experimental).
    turbopackFileSystemCacheForDev: true,
  },
};

export default nextConfig;
