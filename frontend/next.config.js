/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  env: {
    NEXT_PUBLIC_BUILD_DATE: new Date().toISOString(),
  },
  async rewrites() {
    return [
      // These Next.js API route handlers take priority; only unmatched /api/* paths
      // fall through to the gateway rewrite below.
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://api-gateway:8000"}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
