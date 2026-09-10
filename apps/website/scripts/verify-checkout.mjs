// Real browser + production auction Worker, with an isolated fake Stripe API.
// No requests can reach Stripe, production storage, or email providers.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { build } from "esbuild";
import { Miniflare, Response as WorkerResponse } from "miniflare";
import puppeteer from "puppeteer";
import sharp from "sharp";

const appPort = 3119;
const apiPort = 8799;
const site = `http://localhost:${appPort}`;
const directory = await mkdtemp(join(tmpdir(), "fly-checkout-browser-"));
const output = resolve("artifacts/checkout-flow");
await mkdir(output, { recursive: true });
const sessions = new Map();
const checkouts = new Map();
const errors = [];
const requests = [];
let mf;
let browser;
let next;
let serverLog = "";
let latestSession;
let activePage;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForServer() {
  for (let attempt = 0; attempt < 120; attempt++) {
    if (next.exitCode !== null) throw new Error(serverLog);
    try {
      const response = await fetch(site);
      if (response.ok) return;
    } catch {
      /* Next is starting. */
    }
    await sleep(500);
  }
  throw new Error(`Next did not start: ${serverLog}`);
}

try {
  const worker = join(directory, "worker.mjs");
  await build({
    entryPoints: ["worker/api.ts"],
    bundle: true,
    format: "esm",
    platform: "browser",
    target: "es2022",
    outfile: worker,
    external: ["cloudflare:workers", "node:*"],
  });
  mf = new Miniflare({
    name: "checkout-browser-test",
    port: apiPort,
    modules: true,
    modulesRoot: directory,
    scriptPath: worker,
    compatibilityDate: "2026-07-30",
    compatibilityFlags: ["nodejs_compat"],
    durableObjects: { AUCTION: { className: "Auction", useSQLite: true } },
    r2Buckets: ["ARTWORK"],
    bindings: {
      SITE_URL: site,
      STRIPE_API_KEY: "sk_test_browser_fixture",
      STRIPE_WEBHOOK_SECRET: "whsec_browser_fixture",
    },
    outboundService: async (request) => {
      const url = new URL(request.url);
      assert.equal(url.origin, "https://api.stripe.com");
      if (
        url.pathname === "/v1/checkout/sessions" &&
        request.method === "POST"
      ) {
        const form = new URLSearchParams(await request.text());
        const key = request.headers.get("Idempotency-Key");
        let session = [...sessions.values()].find((item) => item.key === key);
        if (!session) {
          const id = `cs_test_browser${sessions.size + 1}`;
          session = {
            id,
            key,
            object: "checkout.session",
            mode: "payment",
            status: "open",
            payment_status: "unpaid",
            currency: "usd",
            livemode: false,
            amount_total: Number(
              form.get("line_items[0][price_data][unit_amount]"),
            ),
            client_reference_id: form.get("client_reference_id"),
            metadata: { bid_id: form.get("metadata[bid_id]") },
            payment_intent: `pi_${id}`,
            customer_details: { email: "browser@example.test" },
            url: `https://checkout.stripe.com/c/pay/${id}`,
          };
          sessions.set(id, session);
          checkouts.set(id, form);
        }
        return WorkerResponse.json(session);
      }
      if (url.pathname.startsWith("/v1/checkout/sessions/"))
        return WorkerResponse.json(
          sessions.get(url.pathname.split("/").at(-1)),
        );
      if (url.pathname === "/v1/refunds") {
        const form = new URLSearchParams(await request.text());
        return WorkerResponse.json({
          id: `re_${form.get("payment_intent")}`,
          status: "succeeded",
        });
      }
      throw new Error(
        `Unexpected Stripe request: ${request.method} ${url.pathname}`,
      );
    },
  });
  await mf.ready;
  next = spawn(
    process.execPath,
    ["node_modules/next/dist/bin/next", "dev", "--port", String(appPort)],
    {
      env: { ...process.env, AUCTION_API_URL: `http://127.0.0.1:${apiPort}` },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  next.stdout.on("data", (chunk) => {
    serverLog += chunk;
  });
  next.stderr.on("data", (chunk) => {
    serverLog += chunk;
  });
  await waitForServer();
  browser = await puppeteer.launch({
    headless: true,
    args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
  });
  const page = await browser.newPage();
  activePage = page;
  await page.setViewport({ width: 1440, height: 1040, deviceScaleFactor: 1 });
  await page.emulateMediaFeatures([
    { name: "prefers-reduced-motion", value: "reduce" },
  ]);
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.setRequestInterception(true);
  page.on("request", async (request) => {
    const url = new URL(request.url());
    if (url.origin === "https://checkout.stripe.com") {
      latestSession = url.pathname.split("/").at(-1);
      await request.respond({
        status: 200,
        contentType: "text/html",
        body: "<title>Isolated Stripe test</title><p>Stripe is simulated for browser verification.</p>",
      });
    } else if (
      url.protocol === "data:" ||
      url.protocol === "blob:" ||
      url.hostname === "localhost" ||
      url.hostname === "127.0.0.1"
    ) {
      if (url.pathname.startsWith("/api/") && request.method() === "POST")
        requests.push({ path: url.pathname, body: request.postData() });
      await request.continue();
    } else await request.abort();
  });
  const readyDialog = async () => {
    try {
      await page.waitForSelector(
        'dialog[open] canvas[data-model-ready="true"][data-render-ready="true"]',
        { timeout: 30000 },
      );
    } catch (error) {
      await page.screenshot({ path: join(output, "failure.png") });
      console.log(
        await page.evaluate(() => ({
          text: document.body.innerText.slice(-7000),
          canvases: [...document.querySelectorAll("canvas")].map((el) => ({
            ...el.dataset,
          })),
          renderErrors: [
            ...document.querySelectorAll("[data-render-error]"),
          ].map((el) => el.dataset.renderError),
        })),
        errors,
      );
      throw error;
    }
  };
  const checkWidth = async () => {
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    assert.equal(
      await page.$eval(
        ".checkout-layout",
        (el) => el.scrollWidth <= el.clientWidth + 1,
      ),
      true,
    );
  };
  const start = async () => {
    await page.$eval(".checkout-button", (el) =>
      el.scrollIntoView({ block: "center", behavior: "instant" }),
    );
    await Promise.all([
      page.waitForNavigation({ waitUntil: "domcontentloaded" }),
      page.click(".checkout-button"),
    ]);
    assert.ok(latestSession);
    return latestSession;
  };
  const paidReturn = async (sessionId) => {
    Object.assign(sessions.get(sessionId), {
      status: "complete",
      payment_status: "paid",
    });
    await page.goto(
      checkouts
        .get(sessionId)
        .get("success_url")
        .replace("{CHECKOUT_SESSION_ID}", sessionId),
    );
    await page.waitForSelector("#brand");
    await readyDialog();
    assert.equal(await page.$("#bid-amount"), null);
    assert.match(
      await page.$eval(".payment-received", (el) => el.textContent),
      /Paid securely/,
    );
  };

  await page.goto(`${site}/?spot=ad-57#live-auction`);
  await readyDialog();
  assert.equal(await page.$("#brand"), null);
  assert.equal(await page.$('input[type="file"]'), null);
  assert.match(
    await page.$eval(".checkout-button", (el) => el.textContent),
    /Claim this spot for \$1/,
  );
  await page.click('[aria-label="Increase bid by one dollar"]');
  assert.match(
    await page.$eval(".checkout-button", (el) => el.textContent),
    /\$2/,
  );
  await checkWidth();
  await page.screenshot({ path: join(output, "01-bid-desktop.png") });
  console.log("Verified desktop bid controls and amount-only checkout form.");
  const cancelled = await start();
  const checkoutBody = JSON.parse(
    requests.find((item) => item.path === "/api/checkout").body,
  );
  assert.deepEqual(Object.keys(checkoutBody).sort(), [
    "acceptedTerms",
    "amount",
    "requestId",
    "slotId",
  ]);
  assert.equal(
    requests.some((item) => item.path === "/api/artwork"),
    false,
  );
  await page.goto(checkouts.get(cancelled).get("cancel_url"));
  await readyDialog();
  assert.equal(await page.$eval("#bid-amount", (el) => el.value), "2");
  const session = await start();
  await paidReturn(session); // Return confirmation recovers payment without a webhook.
  console.log("Verified cancellation and paid return to the details form.");
  assert.equal(
    (await (await fetch(`${site}/api/auction`)).json()).placements["ad-57"],
    undefined,
  );
  await page.screenshot({ path: join(output, "02-details-desktop.png") });
  await page.click(".close-dialog");
  await page.waitForSelector(".checkout-resume button");
  await page.goto(site);
  await page.waitForSelector("#brand");
  assert.equal(sessions.size, 2); // Reopening never starts another payment.

  const logo = join(output, "test-logo.png");
  await sharp(
    Buffer.from(
      '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="320"><rect width="640" height="320" rx="30" fill="#244d30"/><text x="320" y="195" font-size="88" text-anchor="middle" fill="#fff" font-family="sans-serif">STUDIO</text></svg>',
    ),
  )
    .png()
    .toFile(logo);
  await page.type("#brand", "After payment studio");
  await page.type("#brand-url", "https://example.com");
  await page.type("#brand-message", "Added after paying, ready for the road.");
  const file = await page.$('input[type="file"]');
  await file.uploadFile(logo);
  await page.waitForFunction(() =>
    document
      .querySelector(".checkout-visual canvas")
      ?.dataset.textureRevision?.includes("blob:"),
  );
  await page.$eval(".terms-checkbox input", (el) =>
    el.scrollIntoView({ block: "center", behavior: "instant" }),
  );
  await page.click(".terms-checkbox input");
  await page.waitForFunction(
    () => !document.querySelector(".checkout-button").disabled,
  );
  await readyDialog();
  await page.$eval(".dialog-content", (el) => {
    el.scrollTop = 0;
  });
  await page.screenshot({ path: join(output, "03-artwork-desktop.png") });
  const observerContext = await browser.createBrowserContext();
  const observer = await observerContext.newPage();
  observer.on("pageerror", (error) => errors.push(error.message));
  observer.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await observer.goto(site);
  await page.bringToFront();
  await page.$eval(".checkout-button", (el) =>
    el.scrollIntoView({ block: "center", behavior: "instant" }),
  );
  await page.click(".checkout-button");
  await page.waitForFunction(() => !document.querySelector("dialog[open]"), {
    polling: 100,
  });
  await observer.waitForFunction(
    () => document.body.innerText.includes("After payment studio"),
    { polling: 100 },
  );
  const live = await (await fetch(`${site}/api/auction`)).json();
  assert.equal(live.placements["ad-57"].brand, "After payment studio");
  assert.equal(live.totalRaised, 200);
  assert.equal(
    (await fetch(`${site}${live.placements["ad-57"].textureUrl}`)).status,
    200,
  );
  assert.equal(
    requests.filter((item) => item.path === "/api/checkout").length,
    2,
  );
  await page.reload();
  await page.waitForFunction(() =>
    document.body.innerText.includes("After payment studio"),
  );
  assert.equal(await page.$("#brand"), null);
  await observerContext.close();
  console.log(
    "Verified artwork publication, recovery, and independent live updates.",
  );

  // Let an older refund confirmation arrive before the initial auction
  // snapshot. It must not erase the cancelled checkout's spot and amount.
  Object.assign(sessions.get(cancelled), {
    status: "complete",
    payment_status: "paid",
  });
  assert.equal(
    await page.evaluate(
      (sessionId) =>
        Object.keys(localStorage).some((key) => key.endsWith(sessionId)),
      cancelled,
    ),
    true,
    "The cancelled checkout remains saved for payment recovery.",
  );
  const delayedSnapshots = await page.evaluateOnNewDocument(() => {
    const originalFetch = window.fetch.bind(window);
    const ready = new Promise((resolve) => {
      window.releaseAuctionSnapshots = resolve;
    });
    window.fetch = async (...args) => {
      if (args[0] === "/api/auction") await ready;
      return originalFetch(...args);
    };
    const OriginalWebSocket = window.WebSocket;
    window.WebSocket = class extends OriginalWebSocket {
      set onmessage(handler) {
        if (new URL(this.url).pathname !== "/api/live") {
          super.onmessage = handler;
          return;
        }
        super.onmessage = (event) => {
          void ready.then(() => handler?.call(this, event));
        };
      }
    };
  });
  await page.goto(checkouts.get(cancelled).get("cancel_url"));
  await page.waitForSelector("#bid-amount");
  assert.equal(await page.$eval("#bid-amount", (el) => el.value), "2");
  assert.equal(await page.$eval("#bid-amount", (el) => el.min), "3");
  assert.equal(await page.$eval(".checkout-button", (el) => el.disabled), true);
  assert.match(
    await page.$eval("#bid-help", (el) => el.textContent),
    /minimum is now \$3\. Update your bid/,
  );
  await page.waitForFunction(() =>
    document.body.innerText.includes("Your payment has been refunded."),
  );
  await page.evaluate(() => window.releaseAuctionSnapshots());
  await page.removeScriptToEvaluateOnNewDocument(delayedSnapshots.identifier);
  await readyDialog();
  await page.click('[aria-label="Increase bid by one dollar"]');
  assert.equal(await page.$eval("#bid-amount", (el) => el.value), "3");
  assert.equal(
    await page.$eval(".checkout-button", (el) => el.disabled),
    false,
  );
  console.log(
    "Verified refund recovery preserves a cancelled bid below the new minimum.",
  );

  await page.setViewport({
    width: 390,
    height: 844,
    deviceScaleFactor: 1,
    isMobile: true,
    hasTouch: true,
  });
  await page.goto(`${site}/?spot=ad-57#live-auction`);
  await readyDialog();
  await checkWidth();
  await page.screenshot({ path: join(output, "04-bid-mobile.png") });
  await page.$eval(".checkout-button", (el) =>
    el.scrollIntoView({ block: "center", behavior: "instant" }),
  );
  await page.screenshot({ path: join(output, "05-bid-mobile-action.png") });
  const mobileSession = await start();
  await paidReturn(mobileSession);
  await checkWidth();
  await page.screenshot({ path: join(output, "06-details-mobile.png") });
  assert.deepEqual(errors, []);
  await writeFile(
    join(output, "verification.json"),
    JSON.stringify(
      {
        verified: [
          "amount-only checkout",
          "cancel preserves bid",
          "cancel preserves bid after a price increase",
          "background refunds preserve checkout return links",
          "paid return opens details",
          "paid details survive dismissal and reload",
          "artwork preview",
          "publication and independent observer",
          "no repeat charge",
          "mobile layouts",
        ],
        sessions: sessions.size,
        liveRevision: live.revision,
        browserErrors: errors,
      },
      null,
      2,
    ),
  );
  console.log(`Checkout browser verification passed. Screenshots: ${output}`);
} catch (error) {
  if (activePage && !activePage.isClosed()) {
    await activePage
      .screenshot({ path: join(output, "failure.png") })
      .catch(() => {});
    console.log(
      await activePage
        .evaluate(() => ({
          url: location.href,
          storageKeys: Object.keys(localStorage),
          status: document.querySelector(".checkout-status")?.textContent,
          dialog: document.querySelector("dialog")?.innerText,
          errors: [...document.querySelectorAll(".form-error")].map(
            (el) => el.textContent,
          ),
        }))
        .catch(() => null),
    );
  }
  if (mf)
    console.log(
      "Auction state:",
      await (await mf.dispatchFetch(`${site}/api/auction`)).json(),
    );
  console.log("Browser errors:", errors);
  throw error;
} finally {
  await browser?.close();
  next?.kill("SIGTERM");
  if (next && next.exitCode === null)
    await new Promise((resolve) => next.once("exit", resolve));
  await mf?.dispose();
  await rm(directory, { recursive: true, force: true });
}
