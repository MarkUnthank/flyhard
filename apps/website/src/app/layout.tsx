import type { Metadata } from "next";
import "@fontsource-variable/dm-sans";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://thedrivingfly.com"),
  title: "The Driving Fly — Your brand. A car. A fly.",
  icons: { icon: "/favicon.svg" },
  description:
    "Help teach a fly to drive. Pick a spot on our Mini, put your logo on it, and stay until someone pays more. Every empty spot starts at $1.",
  openGraph: {
    siteName: "The Driving Fly",
    title: "Your brand. A car. A fly.",
    description:
      "12 ad spaces. One very small driver. Put your brand on The Driving Fly, from $1.",
    type: "website",
    images: [
      {
        url: "/social/driving-fly-wide-v2.jpg",
        width: 1200,
        height: 630,
        type: "image/jpeg",
        alt: "Your brand. A car. A fly. A green Mini covered in ad spaces, from $1.",
      },
      {
        url: "/social/driving-fly-square-v2.jpg",
        width: 1080,
        height: 1080,
        type: "image/jpeg",
        alt: "The Driving Fly: 12 ad spaces on a green Mini. From $1.",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    creator: "@alright_mark",
    title: "Your brand. A car. A fly.",
    description:
      "12 ad spaces. One very small driver. Put your brand on The Driving Fly, from $1.",
    images: [
      {
        url: "/social/driving-fly-wide-v2.jpg",
        alt: "Your brand. A car. A fly. A green Mini covered in ad spaces, from $1.",
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
