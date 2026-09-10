import type { Metadata } from "next";
import "@fontsource-variable/dm-sans";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://thedrivingfly.com"),
  title: "The Driving Fly — Your brand. A car. A fly.",
  icons: { icon: "/favicon.svg" },
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
        url: "/social/driving-fly-wide-v3.jpg",
        width: 1200,
        height: 630,
        type: "image/jpeg",
        alt: "Your brand. A car. A fly. Seven ad spaces. Outbid a sponsor.",
      },
      {
        url: "/social/driving-fly-square-v3.jpg",
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
        url: "/social/driving-fly-wide-v3.jpg",
        alt: "Your brand. A car. A fly. Seven ad spaces. Outbid a sponsor.",
      },
    ],
  },
  robots: { index: true, follow: true },
};
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
