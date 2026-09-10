import type { MetadataRoute } from "next";
export default function sitemap(): MetadataRoute.Sitemap {
  return ["", "/terms", "/privacy", "/credits"].map((path) => ({
    url: `https://thedrivingfly.com${path}`,
  }));
}
