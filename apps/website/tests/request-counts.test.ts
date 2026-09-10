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
  syncRequestCounts(): Promise<void>;
  testSql(
    query: string,
    ...values: (string | number | null)[]
  ): Promise<Record<string, unknown>[]>;
};

beforeAll(async () => {
  directory = await mkdtemp(join(tmpdir(), "fly-requests-"));
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
      expect(body.query).not.toContain("bot:");
      expect(body.query).toContain("sum { requests }");
      expect(body.variables.from).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(body.variables.to).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(body.query).toContain("0f870574c4a4f0ee249260cb93e3bff6");
      if (fail)
        return Response.json({
          errors: [{ message: "Permission denied" }],
          data: null,
        });
      return Response.json({
        errors: null,
        data: {
          viewer: {
            zones: [
              {
                httpRequests1dGroups: [
                  {
                    sum: { requests: invalid ? -1 : count },
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
  ).json()) as { totalRequests: number | null };

describe("durable historic request counts", () => {
  it("hides an unknown total and does not let page requests trigger analytics queries", async () => {
    // Existing production page-view data must not seed the new request metric.
    await stub.testSql("INSERT INTO counters VALUES ('total_views', 990)");
    await stub.testSql(
      "INSERT INTO counters VALUES ('views_synced_through', ?)",
      Date.now(),
    );
    expect((await snapshot()).totalRequests).toBeNull();
    expect(requests).toBe(0);
    expect(
      (
        await mf.dispatchFetch(
          "https://thedrivingfly.com/api/syncRequestCounts",
          {
            method: "POST",
            headers: { Origin: "https://thedrivingfly.com" },
          },
        )
      ).status,
    ).toBe(404);
    expect(requests).toBe(0);
  });
  it("backfills, replaces daily counts without double counting, and retains older history", async () => {
    // Start within the refresh window, with an older archived daily aggregate.
    await stub.testSql("INSERT INTO request_counts VALUES ('2026-09-08', 100)");
    await stub.testSql(
      "INSERT INTO counters VALUES ('requests_synced_through', ?)",
      Date.now(),
    );
    await stub.syncRequestCounts();
    expect((await snapshot()).totalRequests).toBe(112);
    await stub.syncRequestCounts();
    expect((await snapshot()).totalRequests).toBe(112);
    count = 17;
    await stub.syncRequestCounts();
    expect((await snapshot()).totalRequests).toBe(117);
  });
  it("preserves the last good total and sync position on GraphQL or malformed-data failures", async () => {
    const before = await stub.testSql(
      "SELECT * FROM counters WHERE name = 'requests_synced_through'",
    );
    fail = true;
    await expect(stub.syncRequestCounts()).rejects.toThrow();
    expect((await snapshot()).totalRequests).toBe(117);
    expect(
      await stub.testSql(
        "SELECT * FROM counters WHERE name = 'requests_synced_through'",
      ),
    ).toEqual(before);
    fail = false;
    invalid = true;
    await expect(stub.syncRequestCounts()).rejects.toThrow();
    expect((await snapshot()).totalRequests).toBe(117);
    invalid = false;
    count = 20;
    await stub.syncRequestCounts();
    expect((await snapshot()).totalRequests).toBe(120);
  });
});
