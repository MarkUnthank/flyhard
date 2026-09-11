import { readFile, writeFile, mkdir, mkdtemp, rm } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { build } from "esbuild";
import puppeteer from "puppeteer";

// Local packaging only. The checked-in outputs are published by the Git build.
const root = fileURLToPath(new URL("../", import.meta.url));
const press = join(root, "public/press");
await mkdir(press, { recursive: true });
const temporary = await mkdtemp(join(root, ".press-kit-"));
let browser;
try {
  const modulePath = join(temporary, "content.mjs");
  await build({
    stdin: {
      contents: `import React from 'react'; import { renderToStaticMarkup } from 'react-dom/server'; import FlyMark from './src/components/fly-mark'; export { mediaEntries } from './src/lib/media'; export const mark = renderToStaticMarkup(React.createElement(FlyMark, { size: 512 }));`,
      resolveDir: root,
      loader: "tsx",
    },
    bundle: true,
    packages: "external",
    platform: "node",
    format: "esm",
    outfile: modulePath,
    jsx: "automatic",
  });
  const { mark, mediaEntries } = await import(pathToFileURL(modulePath).href);
  const kit = JSON.parse(
    await readFile(join(root, "src/lib/press-kit.json"), "utf8"),
  );
  const font = await readFile(
    join(
      root,
      "node_modules/@fontsource-variable/dm-sans/files/dm-sans-latin-wght-normal.woff2",
    ),
  );
  const fontFace = `@font-face{font-family:DM;src:url(data:font/woff2;base64,${font.toString("base64")}) format('woff2');font-weight:100 1000;}`;
  const accessibleMark = mark.replace(
    'aria-hidden="true"',
    'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="The Driving Fly mark" style="color:#20211f"',
  );
  const innerMark = mark.slice(
    mark.indexOf(">") + 1,
    mark.lastIndexOf("</svg>"),
  );
  const wordmark = `<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="170" viewBox="0 0 1100 170" role="img" aria-label="The Driving Fly"><style>${fontFace}</style><g color="#20211f" transform="translate(8 12) scale(3.6)">${innerMark}</g><text x="177" y="115" fill="#20211f" font-family="DM,Arial,sans-serif" font-size="104" font-weight="700" letter-spacing="-3">The Driving Fly<tspan fill="#488443">.</tspan></text></svg>`;
  await writeFile(join(press, "the-driving-fly-mark.svg"), accessibleMark);
  await writeFile(join(press, "the-driving-fly-wordmark.svg"), wordmark);
  await writeFile(
    join(press, "DM-Sans-OFL.txt"),
    await readFile(
      join(root, "node_modules/@fontsource-variable/dm-sans/LICENSE"),
    ),
  );

  browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  for (const [name, svg, width, height] of [
    ["mark", accessibleMark, 512, 512],
    ["wordmark", wordmark, 1100, 170],
  ]) {
    await page.setViewport({ width, height, deviceScaleFactor: 2 });
    await page.setContent(
      `<style>body{margin:0;background:transparent}</style>${svg}`,
    );
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({
      path: join(press, `the-driving-fly-${name}.png`),
      omitBackground: true,
    });
  }

  const credits = kit.credits
    .map(
      (credit) =>
        `${credit.title}\n${credit.text}\n${new URL(credit.url, "https://thedrivingfly.com")}\n`,
    )
    .join("\n");
  const filmNotes = mediaEntries
    .slice(0, 5)
    .map(
      (film) =>
        `${film.title}\n${film.category} | ${film.duration} | ${film.audio} | ${film.playback}\nhttps://thedrivingfly.com/media#${film.id}\nDownload: https://thedrivingfly.com/media/${film.id}.mp4\n\n${film.paragraphs.join("\n\n")}\n`,
    )
    .join("\n");
  await writeFile(
    join(press, "credits.txt"),
    `THE DRIVING FLY — CREDITS\nUpdated ${kit.updated}\n\n${credits}`,
  );
  await writeFile(
    join(press, "press-notes.txt"),
    `THE DRIVING FLY — PRESS KIT\nUpdated ${kit.updated}\nhttps://thedrivingfly.com/press\nPress contact: Mark Unthank, ${kit.contact}\n\nPROJECT SUMMARY\n${kit.summary}\n\nBACKGROUND\n${kit.boilerplate}\n\nQUICK FACTS\n${kit.facts.map((fact) => `${fact.label}: ${fact.value}`).join("\n")}\n\nFILMS & CONTEXT\n${filmNotes}\nCREDITS\n${credits}`,
  );
  await writeFile(
    join(press, "captions.txt"),
    kit.stills
      .map(
        (still) =>
          `${still.file}\n${still.title}\n${still.caption}\nCredit: The Driving Fly / Mark Unthank. See credits.txt for third-party attributions.\n`,
      )
      .join("\n"),
  );

  // Python's standard ZIP writer keeps this helper free of new dependencies.
  execFileSync(
    "python3",
    [
      "-c",
      `
import json, pathlib, sys, zipfile
root = pathlib.Path(sys.argv[1]); press = root / 'public/press'
kit = json.loads((root / 'src/lib/press-kit.json').read_text())
files = [(p, p.relative_to(press).as_posix()) for p in press.rglob('*') if p.is_file() and p.suffix != '.zip']
files += [(root / 'public/media' / item['file'], 'stills/' + item['file']) for item in kit['stills']]
files += [(root / 'public/media/attribution.md', 'full-attribution.md')]
with zipfile.ZipFile(press / 'the-driving-fly-press-kit.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for source, name in sorted(files, key=lambda item: item[1]):
        info = zipfile.ZipInfo('the-driving-fly/' + name, (2026, 9, 11, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, source.read_bytes())
print(f'Packaged {len(files)} files: stills, logos, facts, credits and data. Videos linked separately.')
`,
      root,
    ],
    { stdio: "inherit" },
  );
} finally {
  await browser?.close();
  await rm(temporary, { recursive: true, force: true });
}
