export const socialSizes = {
  wide: { width: 1200, height: 630 },
  square: { width: 1080, height: 1080 },
} as const;
export type SocialShape = keyof typeof socialSizes;
export type SocialStatus = {
  revision: number;
  publishedRevision: number | null;
  pending: boolean;
  rendererVersion: string;
  generatedAt: number | null;
  images: Record<SocialShape, string>;
};
export const socialFallbacks: Record<SocialShape, string> = {
  wide: "/social/driving-fly-wide-v4.jpg",
  square: "/social/driving-fly-square-v4.jpg",
};
export const socialImagePath = (key: string, shape: SocialShape) =>
  `/api/social/${key}/${shape}.jpg`;
