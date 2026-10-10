import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    const apiOrigin = process.env.API_INTERNAL_URL || "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${apiOrigin}/api/:path*` },
      { source: "/docs", destination: `${apiOrigin}/docs` },
      { source: "/openapi.json", destination: `${apiOrigin}/openapi.json` },
    ];
  },
};

export default nextConfig;