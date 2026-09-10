import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { build } from "esbuild";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Miniflare, Response } from "miniflare";

let mf: Miniflare;
let directory: string;
let count = 12;
let fail = false;
let invalid = false;
let requests = 0;
let stub: {
  syncPageViews(): Promise<void>;
  testSql(
    query: string,
    ...values: (string | number | null)[]
  ): Promise<Record<string, unknown>[]>;
};

beforeAll(async () => {
  directory = await mkdtemp(join(tmpdir(), "fly-views-"));
  const script = join(directory, "worker.mjs");
  await build({
    entryPoints: ["tests/fixtures/auction-worker.ts"],
    bundle: true,
    format: "esm",
    platform: "browser",
    target: "es2022",
    outfile: script,
    external: ["cloudflare:workers", "node:*"],
  });
  mf = new Miniflare({
    modules: true,
    modulesRoot: directory,
    scriptPath: script,
    compatibilityDate: "2026-08-01",
    compatibilityFlags: ["nodejs_compat"],
    durableObjects: { AUCTION: { className: "Auction", useSQLite: true } },
    r2Buckets: ["ARTWORK"],
    bindings: {
      SITE_URL: "https://thedrivingfly.com",
      CLOUDFLARE_ANALYTICS_TOKEN: "test-only",
    },
    outboundService: async (request: import("miniflare").Request) => {
      requests++;
      expect(request.url).toBe("https://api.cloudflare.com/client/v4/graphql");
      expect(request.headers.get("authorization")).toBe("Bearer test-only");
      const body = (await request.json()) as {
        query: string;
        variables: { from: string; to: string };
      };
      expect(body.query).toContain("bot: 0");
      expect(body.query).toContain("a9425d0f08934c0b919b4c5ff11fb5f7");
      if (fail)
        return Response.json({
          errors: [{ message: "Permission denied" }],
          data: null,
        });
      return Response.json({
        errors: null,
        data: {
          viewer: {
            accounts: [
              {
                rumPageloadEventsAdaptiveGroups: [
                  {
                    count: invalid ? -1 : count,
                    dimensions: { date: body.variables.from.slice(0, 10) },
                  },
                ],
              },
            ],
          },
        },
      });
    },
  });
  const ns = await mf.getDurableObjectNamespace("AUCTION");
  stub = ns.get(ns.idFromName("the-driving-fly-v1")) as unknown as typeof stub;
});
afterAll(async () => {
  await mf?.dispose();
  await rm(directory, { recursive: true, force: true });
});
const snapshot = async () =>
  (await (
    await mf.dispatchFetch("https://thedrivingfly.com/api/auction")
  ).json()) as { totalViews: number | null };

describe("durable historic page views", () => {
  it("hides an unknown total and does not let page requests trigger analytics queries", async () => {
    expect((await snapshot()).totalViews).toBeNull();
    expect(requests).toBe(0);
    expect(
      (
        await mf.dispatchFetch("https://thedrivingfly.com/api/syncPageViews", {
          method: "POST",
          headers: { Origin: "https://thedrivingfly.com" },
        })
      ).status,
    ).toBe(404);
    expect(requests).toBe(0);
  });
  it("backfills, replaces daily counts without double counting, and retains older history", async () => {
    // Start within the refresh window, with an older archived daily aggregate.
    await stub.testSql("INSERT INTO page_views VALUES ('2026-09-08', 100)");
    await stub.testSql(
      "INSERT INTO counters VALUES ('views_synced_through', ?)",
      Date.now(),
    );
    await stub.syncPageViews();
    expect((await snapshot()).totalViews).toBe(112);
    await stub.syncPageViews();
    expect((await snapshot()).totalViews).toBe(112);
    count = 17;
    await stub.syncPageViews();
    expect((await snapshot()).totalViews).toBe(117);
  });
  it("preserves the last good total and sync position on GraphQL or malformed-data failures", async () => {
    const before = await stub.testSql(
      "SELECT * FROM counters WHERE name = 'views_synced_through'",
    );
    fail = true;
    await expect(stub.syncPageViews()).rejects.toThrow();
    expect((await snapshot()).totalViews).toBe(117);
    expect(
      await stub.testSql(
        "SELECT * FROM counters WHERE name = 'views_synced_through'",
      ),
    ).toEqual(before);
    fail = false;
    invalid = true;
    await expect(stub.syncPageViews()).rejects.toThrow();
    expect((await snapshot()).totalViews).toBe(117);
    invalid = false;
    count = 20;
    await stub.syncPageViews();
    expect((await snapshot()).totalViews).toBe(120);
  });
});
