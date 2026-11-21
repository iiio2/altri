import path from "node:path";

import type { NextConfig } from "next";

// Where the FastAPI server listens, as seen from the Next.js server. REST calls go through this rewrite, so the
// browser talks to one origin and the API's HttpOnly session cookie is a first-party cookie of the web app.
// (The live WebSocket connects to the API directly; see lib/live/socket-url.ts.)
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

// The Docker image (apps/web/Dockerfile) sets NEXT_OUTPUT=standalone; local `next start` keeps the default output.
const standalone = process.env.NEXT_OUTPUT === "standalone";

const nextConfig: NextConfig = {
  ...(standalone && {
    output: "standalone",
    // pnpm workspace: trace dependencies from the repo root so the standalone bundle includes them.
    outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
  }),
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
