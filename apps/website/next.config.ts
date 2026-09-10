import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async rewrites() {
    const apiUrl = process.env.AUCTION_API_URL || "http://127.0.0.1:8788";
    return process.env.NODE_ENV === "development"
      ? {
          beforeFiles: [
            {
              source:
                "/social/driving-fly-:shape(wide|square)-v:version(\\d+).jpg",
              destination: `${apiUrl}/api/social/:shape.jpg`,
            },
          ],
          afterFiles: [
            {
              source: "/api/:path*",
              destination: `${apiUrl}/api/:path*`,
            },
          ],
          fallback: [],
        }
      : [];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};
export default nextConfig;
