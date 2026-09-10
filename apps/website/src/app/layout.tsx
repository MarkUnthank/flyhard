import type { Metadata } from "next";
import { connection } from "next/server";
import { getCloudflareContext } from "@opennextjs/cloudflare";
import type { SocialStatus } from "@/lib/social";
import "@fontsource-variable/dm-sans";
import "./globals.css";

const metadata = {
  metadataBase: new URL("https://thedrivingfly.com"),
  title: "The Driving Fly — Your brand. A car. A fly.",
  icons: {
    icon: [
      { url: "/favicon-32x32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon-192x192.png", sizes: "192x192", type: "image/png" },
      { url: "/favicon.png", sizes: "512x512", type: "image/png" },
    ],
    shortcut: "/favicon-32x32.png",
    apple: [
      { url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" },
    ],
  },
  description:
    "Help teach a fly to drive. Pick a spot on our Mini, put your logo on it, and stay until someone pays more. Seven placements. Outbid the current sponsor to make one yours.",
  openGraph: {
    siteName: "The Driving Fly",
    title: "Your brand. A car. A fly.",
    description:
      "7 ad spaces. One very small driver. Outbid a sponsor to put your brand on The Driving Fly.",
    type: "website",
    images: [
      {
        url: "/api/social/wide.jpg",
        width: 1200,
        height: 630,
        type: "image/jpeg",
        alt: "Your brand. A car. A fly. Seven ad spaces. Outbid a sponsor.",
      },
      {
        url: "/api/social/square.jpg",
        width: 1080,
        height: 1080,
        type: "image/jpeg",
        alt: "The Driving Fly: 7 ad spaces on a green Mini. Outbid a sponsor.",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    creator: "@alright_mark",
    title: "Your brand. A car. A fly.",
    description:
      "7 ad spaces. One very small driver. Outbid a sponsor to put your brand on The Driving Fly.",
    images: [
      {
        url: "/api/social/wide.jpg",
        alt: "Your brand. A car. A fly. Seven ad spaces. Outbid a sponsor.",
      },
    ],
  },
  robots: { index: true, follow: true },
} satisfies Metadata;

export async function generateMetadata(): Promise<Metadata> {
  // Metadata must follow the durable published-image pointer on every scrape,
  // rather than freezing the wrap into Next's prerender/HTML cache at build time.
  await connection();
  let images = {
    wide: "/api/social/wide.jpg",
    square: "/api/social/square.jpg",
  };
  let siteUrl = "https://thedrivingfly.com";
  try {
    let response: Response;
    if (process.env.NODE_ENV === "development") {
      siteUrl = "http://localhost:3000";
      response = await fetch("http://127.0.0.1:8788/api/social", {
        cache: "no-store",
      });
    } else {
      const { env } = getCloudflareContext();
      siteUrl = env.SITE_URL;
      response = await env.AUCTION.get(
        env.AUCTION.idFromName("the-driving-fly-v1"),
      ).fetch(new Request(new URL("/api/social", siteUrl)));
    }
    if (!response.ok) throw new Error("Social image status unavailable");
    images = ((await response.json()) as SocialStatus).images;
  } catch {
    // A temporary status failure should not take the homepage down. The aliases
    // still resolve to the last complete pair and are never cached at the origin.
    console.error(
      "Social image metadata unavailable; using current-image aliases",
    );
  }
  return {
    ...metadata,
    metadataBase: new URL(siteUrl),
    openGraph: {
      ...metadata.openGraph,
      images: metadata.openGraph.images.map((image, index) => ({
        ...image,
        url: index === 0 ? images.wide : images.square,
      })),
    },
    twitter: {
      ...metadata.twitter,
      images: [{ ...metadata.twitter.images[0], url: images.wide }],
    },
  };
}
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body>{children}</body>
    </html>
  );
}
