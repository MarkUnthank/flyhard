// Compose versioned Open Graph cards from the verified Blender render.
import sharp from "sharp";
import { mkdir } from "node:fs/promises";
const [source, output = "public/social"] = process.argv.slice(2);
if (!source) throw new Error("Usage: node scripts/build-social.mjs RENDER_PNG [OUTPUT_DIR]");
await mkdir(output, { recursive: true });
const car = await sharp(source).trim({ threshold: 12 }).toBuffer();
const svg = (width, height, body) => Buffer.from(`<svg width="${width}" height="${height}" xmlns="http://www.w3.org/2000/svg"><style>text{font-family:Arial,sans-serif;fill:#20231d}.green{fill:#527a3f}.bold{font-weight:900}</style>${body}</svg>`);
for (const square of [false, true]) {
  const width = square ? 1080 : 1200, height = square ? 1080 : 630;
  let rendered = await sharp(car).resize({width:square?1010:830,height:square?690:550,fit:"inside"}).toBuffer();
  const dims = await sharp(rendered).metadata();
  // Let the studio shadow dissolve into the card rather than end at a rectangle.
  for (const horizontal of [false, true]) {
    const mask = Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${dims.width}" height="${dims.height}"><defs><linearGradient id="fade" x2="${horizontal?1:0}" y2="${horizontal?0:1}"><stop offset="0" stop-color="white" stop-opacity="${horizontal?0:1}"/><stop offset=".04" stop-color="white"/><stop offset=".88" stop-color="white"/><stop offset="1" stop-color="white" stop-opacity="0"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#fade)"/></svg>`);
    rendered = await sharp(rendered).composite([{input:mask,blend:"dest-in"}]).png().toBuffer();
  }
  const left = square ? Math.round((width-dims.width)/2) : width-dims.width-18;
  const top = square ? 335 : Math.round((height-dims.height)/2);
  const text = square
    ? `<text x="54" y="66" font-size="22" font-weight="700" letter-spacing="6">THE <tspan class="green">DRIVING</tspan> FLY</text>
       <text x="50" y="172" font-size="89" class="bold">Your brand.</text><text x="50" y="266" font-size="89" class="bold"><tspan class="green">A car.</tspan> A fly.</text>
       <text x="54" y="1010" font-size="30">7 ad spaces. <tspan class="green" font-weight="700">Outbid a sponsor.</tspan></text><text x="54" y="1050" font-size="23">thedrivingfly.com</text>`
    : `<text x="48" y="67" font-size="20" font-weight="700" letter-spacing="5">THE <tspan class="green">DRIVING</tspan> FLY</text>
       <text x="44" y="196" font-size="74" class="bold">Your brand.</text><text x="44" y="279" font-size="80" class="bold green">A car.</text><text x="44" y="362" font-size="80" class="bold">A fly.</text>
       <text x="48" y="583" font-size="27">7 ad spaces. <tspan class="green" font-weight="700">Outbid a sponsor.</tspan></text><text x="947" y="583" font-size="21">thedrivingfly.com</text>`;
  await sharp({create:{width,height,channels:3,background:"#fafbf8"}})
    .composite([{input:rendered,left,top},{input:svg(width,height,text)}])
    .jpeg({quality:93,mozjpeg:true})
    .toFile(`${output}/driving-fly-${square?"square":"wide"}-v4.jpg`);
}
