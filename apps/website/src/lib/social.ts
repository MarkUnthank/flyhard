import socialSizes from "./social-sizes.json";
export { socialSizes };
export type SocialShape = keyof typeof socialSizes;
export type SocialStatus = {
  revision: number;
  publishedRevision: number | null;
  pending: boolean;
  triggerConfigured: boolean;
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
export function legacySocialAlias(path: string) {
  const match = /^\/social\/driving-fly-(wide|square)-v\d+\.jpg$/.exec(path);
  return match ? `/api/social/${match[1]}.jpg` : null;
}
