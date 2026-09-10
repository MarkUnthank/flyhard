import puppeteer from "puppeteer";
import { readFile } from "node:fs/promises";

const renderOrigin = "https://social.internal";
const sizes = {
  wide: { width: 1200, height: 630 },
  square: { width: 1080, height: 1080 },
};
const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><link rel="stylesheet" href="/social/renderer/index.css"></head><body><div id="card"></div><script src="/social/renderer/index.js"></script></body></html>`;
const contentType = (path) =>
  ({
    js: "text/javascript",
    css: "text/css",
    wasm: "application/wasm",
    woff2: "font/woff2",
    png: "image/png",
  })[path.split(".").at(-1)] ?? "application/octet-stream";

export async function renderSocialCards(snapshot, site) {
  const manifest = JSON.parse(await readFile(".social/manifest.json", "utf8"));
  const resources = new Map();
  for (const path of manifest.assets)
    resources.set(path, await readFile(`public${path}`));
  // Freeze only confirmed public artwork. The page never visits advertisers or
  // fetches a moving live auction while the two sizes are being captured.
  for (const { textureUrl } of Object.values(snapshot.placements)) {
    if (!/^\/api\/artwork\/[a-f0-9-]{36}\.png$/.test(textureUrl))
      throw new Error("Unexpected published artwork URL");
    if (resources.has(textureUrl)) continue;
    const response = await fetch(new URL(textureUrl, site), {
      redirect: "error",
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok)
      throw new Error(`Published artwork returned HTTP ${response.status}`);
    resources.set(textureUrl, Buffer.from(await response.arrayBuffer()));
  }
  const browser = await puppeteer.launch({
    headless: true,
    // GitHub's disposable Linux runner has no GPU. Local Macs use their normal renderer.
    args:
      process.platform === "linux"
        ? [
            "--no-sandbox",
            "--use-angle=swiftshader",
            "--enable-unsafe-swiftshader",
          ]
        : [],
  });
  try {
    const images = {};
    for (const [shape, size] of Object.entries(sizes)) {
      const page = await browser.newPage();
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      page.setDefaultTimeout(90_000);
      await page.setViewport({ ...size, deviceScaleFactor: 1 });
      await page.emulateMediaFeatures([
        { name: "prefers-reduced-motion", value: "reduce" },
      ]);
      await page.evaluateOnNewDocument((placements) => {
        window.__SOCIAL_PLACEMENTS__ = placements;
      }, snapshot.placements);
      await page.setRequestInterception(true);
      page.on("request", async (request) => {
        try {
          const url = new URL(request.url());
          if (["blob:", "data:"].includes(url.protocol))
            return await request.continue();
          if (url.origin !== renderOrigin || request.method() !== "GET")
            return await request.abort();
          if (url.pathname === `/${shape}` && request.isNavigationRequest())
            return await request.respond({
              status: 200,
              contentType: "text/html",
              body: html,
            });
          const body = resources.get(url.pathname);
          if (body)
            return await request.respond({
              status: 200,
              contentType: contentType(url.pathname),
              body,
            });
          await request.abort();
        } catch (error) {
          errors.push(error.message);
          if (!request.isInterceptResolutionHandled())
            await request.abort().catch(() => {});
        }
      });
      await page.goto(`${renderOrigin}/${shape}`, {
        waitUntil: "domcontentloaded",
      });
      try {
        await page.waitForFunction(() => {
          if (document.querySelector('[data-render-error="true"]'))
            throw new Error("Model or artwork failed to load");
          return (
            document.fonts.status === "loaded" &&
            !!document.querySelector('canvas[data-render-ready="true"]')
          );
        });
      } catch {
        throw new Error(
          `The ${shape} card did not finish rendering. ${errors.join("; ")}`,
        );
      }
      if (errors.length) throw new Error(errors.join("; "));
      images[shape] = await page.screenshot({
        type: "jpeg",
        quality: 92,
        captureBeyondViewport: false,
      });
      await page.close();
    }
    return images;
  } finally {
    await browser.close();
  }
}
