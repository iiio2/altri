import type { NextConfig } from "next";

// Where the FastAPI server listens, as seen from the Next.js server. REST calls go through this rewrite, so the
// browser talks to one origin and the API's HttpOnly session cookie is a first-party cookie of the web app.
// (The live WebSocket connects to the API directly; see lib/live/socket-url.ts.)
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  reactCompiler: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${API_URL}/api/v1/:path*` }];
  },
};

export default nextConfig;
